from voteit.speaker.abcs import ListMethod
from voteit.speaker.registries import list_method


@list_method
class Simple(ListMethod):
    title = "Simple flat list that maintains order chronologically"
    description = "It's just a queue with no settings. It won't prioritise speakers."
