"""Opt-in Isaac 5.1 teardown diagnostic; not proven exhaustive sensor cleanup.

Sequence from the shutdown audit (2026-11-14), based on Isaac v5.1.0 Camera
source and NVIDIA's callback-lifetime clarification:
https://github.com/isaac-sim/IsaacSim/issues/380#issuecomment-3772804421
Private callback fields are deliberately restricted to Isaac 5.1.0. The two
updates below are experimental allowances for deferred destruction, not a fence.
"""
import traceback


def cleanup_sensors(app, world, camera, world_type, version, checkpoint):
    """Attempt each teardown step and normal close, returning Python failures.

    ``checkpoint`` persists and flushes markers before and after each operation.
    Imports stay inside this function, after SimulationApp has been created.
    Native aborts are not intercepted; the last persisted marker locates them.
    """
    errors = []

    def step(name, operation):
        checkpoint(name, 'before')
        try:
            result = operation()
        except BaseException as exc:
            errors.append(exc)
            traceback.print_exc()
            checkpoint(name, 'after', status='failed',
                       error_type=type(exc).__name__, error=str(exc))
            return None
        checkpoint(name, 'after', status='completed')
        return result

    if world is not None:
        step('world.stop', world.stop)
    if camera is not None:
        step('camera.pause', camera.pause)

        def clear_callback(field):
            if version is None or version.split('.')[:3] != ['5', '1', '0']:
                raise RuntimeError('Private camera callback cleanup requires Isaac 5.1.0')
            # Assigning None releases the subscription; do not call unsubscribe().
            setattr(camera, field, None)

        for field in ('_stage_open_callback', '_timer_reset_callback'):
            step(f'camera.{field}=None', lambda field=field: clear_callback(field))
        step('camera.destroy', camera.destroy)
    if world is not None:
        step('world.clear_all_callbacks', world.clear_all_callbacks)
    if world_type is not None:
        step('World.clear_instance', world_type.clear_instance)

    def viewport_windows():
        from omni.kit.viewport.window import get_viewport_window_instances
        return list(get_viewport_window_instances(usd_context_name=None))

    windows = step('viewport.enumerate', viewport_windows)
    if windows is not None:
        for index, window in enumerate(windows):
            step(f'viewport[{index}].destroy', window.destroy)
    for index in range(2):
        step(f'app.update[{index}]', app.update)
    # Always attempt regular close, even if an earlier diagnostic step failed.
    step('app.close', lambda: app.close(skip_cleanup=False))
    return errors
