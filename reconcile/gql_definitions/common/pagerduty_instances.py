"""
Generated by qenerate plugin=pydantic_v1. DO NOT MODIFY MANUALLY!
"""
from collections.abc import Callable  # noqa: F401 # pylint: disable=W0611
from enum import Enum  # noqa: F401 # pylint: disable=W0611
from typing import (  # noqa: F401 # pylint: disable=W0611
    Any,
    Optional,
    Union,
)

from pydantic import (  # noqa: F401 # pylint: disable=W0611
    BaseModel,
    Extra,
    Field,
    Json,
)

from reconcile.gql_definitions.fragments.vault_secret import VaultSecret


DEFINITION = """
fragment VaultSecret on VaultSecret_v1 {
    path
    field
    version
    format
}

query PagerduytInstances {
  pagerduty_instances: pagerduty_instances_v1 {
    name
    token {
      ...VaultSecret
    }
  }
}
"""


class PagerDutyInstanceV1(BaseModel):
    name: str = Field(..., alias="name")
    token: VaultSecret = Field(..., alias="token")

    class Config:
        smart_union = True
        extra = Extra.forbid


class PagerduytInstancesQueryData(BaseModel):
    pagerduty_instances: Optional[list[PagerDutyInstanceV1]] = Field(
        ..., alias="pagerduty_instances"
    )

    class Config:
        smart_union = True
        extra = Extra.forbid


def query(query_func: Callable, **kwargs: Any) -> PagerduytInstancesQueryData:
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
        PagerduytInstancesQueryData: queried data parsed into generated classes
    """
    raw_data: dict[Any, Any] = query_func(DEFINITION, **kwargs)
    return PagerduytInstancesQueryData(**raw_data)
