from .models import UserAuditLog


def log_user_event(
    *,
    action,
    actor=None,
    target=None,
    changes=None,
    note='',
    source='live',
):
    return UserAuditLog.objects.create(
        action=action,
        actor=actor,
        actor_name=actor.full_name if actor else '',
        actor_email=actor.email if actor else '',
        actor_role=actor.role if actor else '',
        target=target,
        target_name=target.full_name if target else '',
        target_email=target.email if target else '',
        target_phone=target.phone if target else '',
        target_role=target.role if target else '',
        changes=changes or {},
        note=note,
        source=source,
    )
