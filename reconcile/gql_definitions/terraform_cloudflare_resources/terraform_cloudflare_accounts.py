"""
Generated by qenerate plugin=pydantic_v1. DO NOT MODIFY MANUALLY!
"""
from typing import (  # noqa: F401 # pylint: disable=W0611
    Any,
    Callable,
    Optional,
    Union,
)

from pydantic import (  # noqa: F401 # pylint: disable=W0611
    BaseModel,
    Extra,
    Field,
    Json,
)


DEFINITION = """
query TerraformCloudflareAccounts {
  accounts: cloudflare_accounts_v1 {
    name
    providerVersion
    apiCredentials {
      path
      field
    }
    terraformStateAccount {
      name
      automationToken {
        path
        field
      }
      terraformState {
        provider
        bucket
        region
        integrations {
          integration
          key
        }
      }
    }
  }
}
"""


class VaultSecretV1(BaseModel):
    path: str = Field(..., alias="path")
    field: str = Field(..., alias="field")

    class Config:
        smart_union = True
        extra = Extra.forbid


class AWSAccountV1_VaultSecretV1(BaseModel):
    path: str = Field(..., alias="path")
    field: str = Field(..., alias="field")

    class Config:
        smart_union = True
        extra = Extra.forbid


class AWSTerraformStateIntegrationsV1(BaseModel):
    integration: str = Field(..., alias="integration")
    key: str = Field(..., alias="key")

    class Config:
        smart_union = True
        extra = Extra.forbid


class TerraformStateAWSV1(BaseModel):
    provider: str = Field(..., alias="provider")
    bucket: str = Field(..., alias="bucket")
    region: str = Field(..., alias="region")
    integrations: list[AWSTerraformStateIntegrationsV1] = Field(
        ..., alias="integrations"
    )

    class Config:
        smart_union = True
        extra = Extra.forbid


class AWSAccountV1(BaseModel):
    name: str = Field(..., alias="name")
    automation_token: AWSAccountV1_VaultSecretV1 = Field(..., alias="automationToken")
    terraform_state: Optional[TerraformStateAWSV1] = Field(..., alias="terraformState")

    class Config:
        smart_union = True
        extra = Extra.forbid


class CloudflareAccountV1(BaseModel):
    name: str = Field(..., alias="name")
    provider_version: str = Field(..., alias="providerVersion")
    api_credentials: VaultSecretV1 = Field(..., alias="apiCredentials")
    terraform_state_account: AWSAccountV1 = Field(..., alias="terraformStateAccount")

    class Config:
        smart_union = True
        extra = Extra.forbid


class TerraformCloudflareAccountsQueryData(BaseModel):
    accounts: Optional[list[CloudflareAccountV1]] = Field(..., alias="accounts")

    class Config:
        smart_union = True
        extra = Extra.forbid


def query(query_func: Callable, **kwargs) -> TerraformCloudflareAccountsQueryData:
    """
    This is a convenience function which queries and parses the data into
    concrete types. It should be compatible with most GQL clients.
    You do not have to use it to consume the generated data classes.
    Alternatively, you can also mime and alternate the behavior
    of this function in the caller.

    Parameters:
        query_func (Callable): Function which queries your GQL Server
        kwargs: optional arguments that will be passed to the query function

    Returns:
        TerraformCloudflareAccountsQueryData: queried data parsed into generated classes
    """
    raw_data: dict[Any, Any] = query_func(DEFINITION, **kwargs)
    return TerraformCloudflareAccountsQueryData(**raw_data)
