import base64
import functools
import logging
import os
import threading
import time
from collections.abc import Mapping
from typing import Optional

import hvac
import requests
from hvac.exceptions import InvalidPath
from requests.adapters import HTTPAdapter
from sretoolbox.utils import retry

from reconcile.utils.config import get_config

LOG = logging.getLogger(__name__)
VAULT_AUTO_REFRESH_INTERVAL = int(os.getenv("VAULT_AUTO_REFRESH_INTERVAL") or 600)


class PathAccessForbidden(Exception):
    pass


class SecretNotFound(Exception):
    pass


class SecretAccessForbidden(Exception):
    pass


class SecretVersionIsNone(Exception):
    pass


class SecretVersionNotFound(Exception):
    pass


class SecretFieldNotFound(Exception):
    pass


class VaultConnectionError(Exception):
    pass


SECRET_VERSION_LATEST = "LATEST"


class _VaultClient:
    """
    A class representing a Vault client. Allows read/write operations.
    The client caches read requests in-memory if the request is made
    to a versioned KV engine (v2), since that includes both a path
    and a version (no invalidation required).
    """

    def __init__(
        self,
        server: Optional[str] = None,
        role_id: Optional[str] = None,
        secret_id: Optional[str] = None,
        auto_refresh: bool = True,
    ):
        config = get_config()

        server = config["vault"]["server"] if server is None else server
        self.role_id = config["vault"]["role_id"] if role_id is None else role_id
        self.secret_id = (
            config["vault"]["secret_id"] if secret_id is None else secret_id
        )

        # This is a threaded world. Let's define a big
        # connections pool to live in that world
        # (this avoids the warning "Connection pool is
        # full, discarding connection: vault.devshift.net")
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100)
        session.mount("https://", adapter)
        self._client = hvac.Client(url=server, session=session)

        authenticated = False
        for _ in range(0, 3):
            try:
                self._refresh_client_auth()
                authenticated = self._client.is_authenticated()
                break
            except requests.exceptions.ConnectionError:
                time.sleep(1)

        if not authenticated:
            raise VaultConnectionError()

        if auto_refresh:
            t = threading.Thread(target=self._auto_refresh_client_auth, daemon=True)
            t.start()

    def _auto_refresh_client_auth(self):
        """
        Thread that periodically refreshes the vault token
        """
        while True:
            time.sleep(VAULT_AUTO_REFRESH_INTERVAL)
            LOG.debug("auto refresh client auth")
            self._refresh_client_auth()

    def _refresh_client_auth(self):
        self._client.auth_approle(self.role_id, self.secret_id)

    @retry()
    def read_all_with_version(self, secret: Mapping) -> tuple[Mapping, Optional[str]]:
        """Returns a dictionary of keys and values in a Vault secret and the
        version of the secret, for V1 secrets, version will be None.

        The input secret is a dictionary which contains the following fields:
        * path - path to the secret in Vault
        * version (optional) - secret version to read (if this is
                               a v2 KV engine)
        """
        secret_path = secret["path"]
        secret_version = secret.get("version")

        kv_version = self._get_mount_version_by_secret_path(secret_path)

        data = None
        if kv_version == 2:
            data, version = self._read_all_v2(secret_path, secret_version)
        else:
            secret_data = self._read_all_v1(secret_path)
            version = None
            data = secret_data

        if data is None:
            raise SecretNotFound

        return data, version

    @retry()
    def read_all(self, secret: Mapping) -> dict:
        """Returns a dictionary of keys and values in a Vault secret.

        The input secret is a dictionary which contains the following fields:
        * path - path to the secret in Vault
        * version (optional) - secret version to read (if this is
                               a v2 KV engine)
        """
        return self.read_all_with_version(secret)[0]

    def _get_mount_version_by_secret_path(self, path):
        path_split = path.split("/")
        mount_point = path_split[0]
        return self._get_mount_version(mount_point)

    @functools.lru_cache(maxsize=128)
    def _get_mount_version(self, mount_point):
        try:
            self._client.secrets.kv.v2.read_configuration(mount_point)
            version = 2
        except Exception:
            version = 1

        return version

    @functools.lru_cache(maxsize=2048)
    def _read_all_v2(
        self, path: str, version: Optional[str]
    ) -> tuple[dict, Optional[str]]:
        path_split = path.split("/")
        mount_point = path_split[0]
        read_path = "/".join(path_split[1:])
        if version is None:
            msg = "version can not be null " f"for secret with path '{path}'."
            raise SecretVersionIsNone(msg)
        elif version == SECRET_VERSION_LATEST:
            # https://github.com/hvac/hvac/blob/
            # ec048ded30d21c13c21cfa950d148c8bfc1467b0/
            # hvac/api/secrets_engines/kv_v2.py#L85
            version = None
        try:
            secret = self._client.secrets.kv.v2.read_secret_version(
                mount_point=mount_point,
                path=read_path,
                version=version,
            )
        except InvalidPath:
            msg = f"version '{version}' not found " f"for secret with path '{path}'."
            raise SecretVersionNotFound(msg)
        except hvac.exceptions.Forbidden:
            msg = f"permission denied accessing secret '{path}'"
            raise SecretAccessForbidden(msg)
        if secret is None or "data" not in secret or "data" not in secret["data"]:
            raise SecretNotFound(path)

        data = secret["data"]["data"]
        secret_version = secret["data"]["metadata"]["version"]
        return data, secret_version

    def _read_all_v1(self, path):
        try:
            secret = self._client.read(path)
        except hvac.exceptions.Forbidden:
            msg = f"permission denied accessing secret '{path}'"
            raise SecretAccessForbidden(msg)

        if secret is None or "data" not in secret:
            raise SecretNotFound(path)

        return secret["data"]

    @retry()
    def read(self, secret):
        """Returns a value of a key in a Vault secret.

        The input secret is a dictionary which contains the following fields:
        * path - path to the secret in Vault
        * field - the key to read from the secret
        * format (optional) - plain or base64 (defaults to plain)
        * version (optional) - secret version to read (if this is
                               a v2 KV engine)
        """
        secret_path = secret["path"]
        secret_field = secret["field"]
        secret_format = secret.get("format", "plain")
        secret_version = secret.get("version")

        kv_version = self._get_mount_version_by_secret_path(secret_path)

        data = None
        if kv_version == 2:
            data = self._read_v2(secret_path, secret_field, secret_version)
        else:
            data = self._read_v1(secret_path, secret_field)

        if data is None:
            raise SecretNotFound

        return (
            base64.b64decode(data).decode("utf-8")
            if secret_format == "base64"
            else data
        )

    def _read_v2(self, path, field, version):
        data, _ = self._read_all_v2(path, version)
        try:
            secret_field = data[field]
        except KeyError:
            raise SecretFieldNotFound(f"{path}/{field} ({version})")
        return secret_field

    def _read_v1(self, path, field):
        data = self._read_all_v1(path)
        try:
            secret_field = data[field]
        except KeyError:
            raise SecretFieldNotFound("{}/{}".format(path, field))
        return secret_field

    @retry()
    def write(
        self, secret: Mapping, decode_base64: bool = True, force: bool = False
    ) -> None:
        """Writes a dictionary of keys and values to a Vault secret.

        The input secret is a dictionary which contains the following fields:
        * path - path to the secret in Vault
        * data - data (dictionary) to write
        """
        secret_path = secret["path"]
        b64_data = secret["data"]
        if decode_base64:
            data = {
                k: base64.b64decode(v or "").decode("utf-8")
                for k, v in b64_data.items()
            }
        else:
            data = b64_data

        kv_version = self._get_mount_version_by_secret_path(secret_path)
        if kv_version == 2:
            self._write_v2(secret_path, data, force)
        else:
            self._write_v1(secret_path, data)

    def _write_v2(self, path: str, data: Mapping, force: bool = False) -> None:
        path_split = path.split("/")
        mount_point = path_split[0]
        write_path = "/".join(path_split[1:])

        try:
            current_data, _ = self._read_all_v2(path, version=SECRET_VERSION_LATEST)
            if current_data == data and not force:
                logging.debug(f"current data is up-to-date, skipping {path}")
                return
        except SecretVersionNotFound:
            # if the secret is not found we need to write it
            logging.debug(f"secret not found in {path}, will create it")

        try:
            self._client.secrets.kv.v2.create_or_update_secret(
                mount_point=mount_point,
                path=write_path,
                secret=data,
            )
            self._read_all_v2.cache_clear()
        except hvac.exceptions.Forbidden:
            msg = f"permission denied accessing secret '{path}'"
            raise SecretAccessForbidden(msg)

    def _write_v1(self, path, data):
        try:
            self._client.write(path, **data)
        except hvac.exceptions.Forbidden:
            msg = f"permission denied accessing secret '{path}'"
            raise SecretAccessForbidden(msg)

    def _list_kv2(self, path: str) -> dict:
        try:
            mount_point, secret_path = path.split("/", 1)
            response = self._client.secrets.kv.v2.list_secrets(
                mount_point=mount_point, path=secret_path
            )
            return response
        except hvac.exceptions.Forbidden:
            msg = f"permission denied accessing path '{path}'"
            raise PathAccessForbidden(msg)

    def _list(self, path: str) -> dict:
        try:
            return self._client.list(path)
        except hvac.exceptions.Forbidden:
            msg = f"permission denied accessing path '{path}'"
            raise PathAccessForbidden(msg)

    def list(self, path: str) -> list[str]:
        """Returns a list of secrets in a given path."""
        kv_version = self._get_mount_version_by_secret_path(path)
        if kv_version == 2:
            path_list = self._list_kv2(path)
        else:
            path_list = self._list(path)

        return path_list["data"]["keys"] or []

    def list_all(self, path):
        """Returns a list of secrets in a given path and
        all its subpaths."""
        secrets = []
        for secret in self.list(path):
            secret_path = f"{path}{secret}"
            if secret.endswith("/"):
                secrets.extend(self.list_all(secret_path))
            else:
                secrets.append(secret_path)
        return secrets


class VaultClient:

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = _VaultClient(*args, **kwargs)
            return cls._instance

        try:
            is_authenticated = cls._instance._client.is_authenticated()
        except requests.exceptions.ConnectionError:
            is_authenticated = False

        if not is_authenticated:
            cls._instance = _VaultClient(*args, **kwargs)
            return cls._instance

        return cls._instance
