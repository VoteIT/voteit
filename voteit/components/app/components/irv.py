from voteit.components.abcs import ComponentAdapter
from voteit.components.registries import organisation_components


@organisation_components
class RepeatedIRV(ComponentAdapter):
    name = "repeated_irv"
    title = "Repeated IRV"
