# voteit/presence

Deprecated, replaced by `voteit.active`. Being removed in two steps:

1. **Done** - `0008_delete_presence` deletes the `presence_check` meeting components and
   drops both models. `models.py` is empty; the app stays installed only so the
   migration can run. `Presence.user` was `RESTRICT` and blocked deleting users.
2. **Later** - once every deployment has run 0008, remove `voteit.presence` from
   `INSTALLED_APPS`, delete the package and run `remove_stale_contenttypes`.

Rolling back to a release that still has the models will break cascading deletes of
meetings and users, since they query the dropped tables.

`voteit.poll.app.er_policies.presence_check.PresenceCheckPolicy` is not part of this
app and stays registered for good. Old meetings may have `er_policy_name="presence_check"`
and old electoral registers `source="presence_check"`; the frontend looks up their
title in `/electoral-register-policies/`. Its `get_voters` always raises.

Dialect YAML may still list `presence_check` under `block_components`. That's harmless:
names there aren't checked against the component registry.
