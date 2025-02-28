import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from typing import (
    Optional,
    Union,
)

from terrascript import (
    Backend,
    Output,
    Resource,
    Terraform,
    Terrascript,
    Variable,
    provider,
)

from reconcile.utils.external_resource_spec import (
    ExternalResourceSpec,
    ExternalResourceSpecInventory,
)
from reconcile.utils.terraform.config import TerraformS3BackendConfig
from reconcile.utils.terraform.config_client import TerraformConfigClient
from reconcile.utils.terrascript.cloudflare_resources import (
    cloudflare_account,
    create_cloudflare_terrascript_resource,
)

TMP_DIR_PREFIX = "terrascript-cloudflare-"

DEFAULT_CLOUDFLARE_ACCOUNT_TYPE = "standard"
DEFAULT_CLOUDFLARE_ACCOUNT_2FA = False
DEFAULT_IS_MANAGED_CLOUDFLARE_ACCOUNT = True


@dataclass
class CloudflareAccountConfig:
    """Configuration related to authenticating API calls to Cloudflare."""

    name: str
    api_token: str
    account_id: str
    enforce_twofactor: bool = DEFAULT_CLOUDFLARE_ACCOUNT_2FA
    type: str = DEFAULT_CLOUDFLARE_ACCOUNT_TYPE
    is_managed_account: bool = DEFAULT_IS_MANAGED_CLOUDFLARE_ACCOUNT


def create_cloudflare_terrascript(
    account_config: CloudflareAccountConfig,
    backend_config: TerraformS3BackendConfig,
    provider_version: str,
    is_managed_account: bool = True,
) -> Terrascript:
    """
    Configures a Terrascript class with the required provider(s) and backend
    configuration.

    This is offloaded to a separate function to avoid mixing additional
    logic into TerrascriptCloudflareClient.

    :param account_config: CloudflareAccount configuration.
    :param backend_config: S3 as backend to store Terraform state.
    :param provider_version: Terraform Cloudflare provider version.
    :is_managed_account:
            If the target cloudflare account is being managed by the caller or not.
            Currently this is deferred to terraform-cloudflare-resources.
            Until further improvement(Tracked by APPSRE-7035),
            this argument can be set to False in other integrations.
            Defaults to True.

    :return: a Terrascript object that contains corresponding resources
    """
    terrascript = Terrascript()

    backend = Backend(
        "s3",
        access_key=backend_config.access_key,
        secret_key=backend_config.secret_key,
        bucket=backend_config.bucket,
        key=backend_config.key,
        region=backend_config.region,
    )

    required_providers = {
        "cloudflare": {
            "source": "cloudflare/cloudflare",
            "version": provider_version,
        }
    }

    terrascript += Terraform(backend=backend, required_providers=required_providers)

    terrascript += provider.cloudflare(
        api_token=account_config.api_token,
        account_id=account_config.account_id,  # needed for some resources, see note below
    )

    cloudflare_account_values = {
        "name": account_config.name,
        "enforce_twofactor": account_config.enforce_twofactor,
        "type": account_config.type,
    }

    if is_managed_account:
        terrascript += cloudflare_account(
            account_config.name,
            **cloudflare_account_values,
        )

    # Some resources need "account_id" to be set at the resource level
    # The cloudflare provider is being migrated from settings account_id at the provider
    # level to requiring it at the resource level, for resources that needs it.
    # This is also listed in version 4.x breaking changes:
    #   https://github.com/cloudflare/terraform-provider-cloudflare/issues/1646
    terrascript += Variable(
        "account_id", type="string", default=account_config.account_id
    )

    return terrascript


class TerrascriptCloudflareClient(TerraformConfigClient):
    """
    Build the Terrascript configuration, collect resources, and return Terraform JSON
    configuration.

    There's actually very little that's specific to Cloudflare in this class. This could
    become a more general TerrascriptClient that could in theory support any resource
    types with some minor modifications to how resource classes (self._resource_classes)
    are tracked.
    """

    def __init__(
        self,
        ts_client: Terrascript,
    ) -> None:
        self._terrascript = ts_client
        self._resource_specs: ExternalResourceSpecInventory = {}

    def add_spec(self, spec: ExternalResourceSpec) -> None:
        self._resource_specs[spec.id_object()] = spec

    def populate_resources(self) -> None:
        """
        Add the resource spec to Terrascript using the resource-specific classes
        to determine which resources to create.
        """
        for spec in self._resource_specs.values():
            resources_to_add = create_cloudflare_terrascript_resource(spec)
            self._add_resources(resources_to_add)

    def dump(self, existing_dir: Optional[str] = None) -> str:
        """Write the Terraform JSON representation of the resources to disk"""
        if existing_dir is None:
            working_dir = tempfile.mkdtemp(prefix=TMP_DIR_PREFIX)
        else:
            working_dir = existing_dir
        with open(working_dir + "/config.tf.json", "w") as terraform_config_file:
            terraform_config_file.write(self.dumps())

        return working_dir

    def dumps(self) -> str:
        """Return the Terraform JSON representation of the resources"""
        return str(self._terrascript)

    def _add_resources(self, tf_resources: Iterable[Union[Resource, Output]]) -> None:
        for resource in tf_resources:
            self._terrascript.add(resource)
