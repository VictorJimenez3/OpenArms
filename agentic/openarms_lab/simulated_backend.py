"""Mock action transport connected to a separate synthetic bench environment."""
from .backends import MockBackend


class SceneBackend(MockBackend):
    def __init__(self, scene_service, **kwargs):
        super().__init__(**kwargs)
        self.scene_service = scene_service
        self.session_id = None

    def bind_session(self, session_id):
        self.session_id = session_id

    def prepare(self):
        super().prepare()
        if self.session_id:
            self.scene_service.world(self.session_id).reset()

    async def execute_step(self, request_id, arguments, progress, *, operation='mock_prepared_sample'):
        if not self.session_id:
            raise RuntimeError('Synthetic environment has no session binding.')

        async def environment_progress(phase):
            if phase == 'mock_dose':
                self.scene_service.world(self.session_id).apply_sample(arguments['condition_id'])
            await progress(phase)

        options = {} if operation == 'mock_prepared_sample' else {'operation': operation}
        result = await super().execute_step(request_id, arguments, environment_progress, **options)
        if result['status'] == 'completed':
            world = self.scene_service.world(self.session_id)
            if operation == 'mock_pick_up':
                world.cup_held = True
            elif operation == 'mock_put_down':
                world.cup_held, world.cup_station = False, arguments['station']
            elif operation == 'mock_pour':
                world.apply_sample(world.sample_condition)
        return result
