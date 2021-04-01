from voteit.core.component import Registry
from voteit.organisation.abcs import ProviderResponseAdapter

provider_response_adapters = Registry(ProviderResponseAdapter)
