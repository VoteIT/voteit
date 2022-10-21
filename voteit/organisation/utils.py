def get_provider_response_adapters():
    from .registries import provider_response_adapters

    return provider_response_adapters


# def annotate_org_from_actor():
#     qs = (
#         LogEntry.objects.exclude(actor__isnull=True)
#         .exclude(additional_data__has_key="o")
#         .exclude(
#             actor__organisation__isnull=True,
#         )
#     )
#     for log in qs:
#         if log.additional_data is None:
#             log.additional_data = {"o": log.actor.organisation_id}
#         else:
#             log.additional_data["o"] = log.actor.organisation_id
#         log.save()
