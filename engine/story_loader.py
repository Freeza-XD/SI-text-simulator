import json
from collections import OrderedDict
from pathlib import Path
from threading import RLock


class StoryLoaderError(Exception):
    pass


class StoryLoader:
    def __init__(self, stories_dir: Path, story_slug: str, cache_max_size: int = 1000, validate_links: bool = True):
        self.stories_dir = stories_dir
        self.story_slug = story_slug
        self.cache_max_size = cache_max_size
        self._lock = RLock()
        self._cache = OrderedDict()
        self._scene_index = {}
        self._story_dir = None
        self._legacy_file = None
        self._legacy_data = None

        self._resolve_story_path()
        self._build_index()
        if validate_links:
            self.validate_scene_links()

    def _resolve_story_path(self):
        candidate_dir = self.stories_dir / self.story_slug
        candidate_file = self.stories_dir / f'{self.story_slug}.json'

        if candidate_dir.is_dir():
            self._story_dir = candidate_dir
            return

        if candidate_file.is_file():
            self._legacy_file = candidate_file
            return

        raise StoryLoaderError(
            f"Story '{self.story_slug}' not found in {self.stories_dir}. "
            "Expected either a directory or a JSON file."
        )

    def _build_index(self):
        if self._story_dir is not None:
            self._scene_index.clear()
            for scene_path in sorted(self._story_dir.glob('*.json')):
                scene_id = scene_path.stem
                if scene_id in self._scene_index:
                    raise StoryLoaderError(f'Duplicate scene ID "{scene_id}" in {self._story_dir}')
                self._scene_index[scene_id] = scene_path

            if not self._scene_index:
                raise StoryLoaderError(f'No scene files found in {self._story_dir}')
        else:
            self._scene_index.clear()

    def reload(self):
        with self._lock:
            self._cache.clear()
            self._legacy_data = None
            self._build_index()
            self.validate_scene_links()

    def _cache_scene(self, scene_id: str, scene_data: dict):
        self._cache[scene_id] = scene_data
        self._cache.move_to_end(scene_id)
        while len(self._cache) > self.cache_max_size:
            self._cache.popitem(last=False)

    def _load_scene_from_file(self, scene_id: str):
        scene_path = self._scene_index.get(scene_id)
        if scene_path is None:
            raise StoryLoaderError(f'Scene "{scene_id}" not found in {self._story_dir}')

        raw_text = scene_path.read_text(encoding='utf-8')
        scene_data = json.loads(raw_text)
        if not isinstance(scene_data, dict):
            raise StoryLoaderError(f'Scene file {scene_path} must contain an object')

        scene_data.setdefault('id', scene_id)
        self._cache_scene(scene_id, scene_data)
        return scene_data

    def _load_legacy_story(self):
        if self._legacy_data is not None:
            return self._legacy_data

        raw_text = self._legacy_file.read_text(encoding='utf-8')
        story_data = json.loads(raw_text)
        if not isinstance(story_data, dict):
            raise StoryLoaderError(f'Legacy story file {self._legacy_file} must contain an object')

        self._legacy_data = story_data
        return story_data

    def get_scene(self, scene_id: str):
        with self._lock:
            if scene_id in self._cache:
                return self._cache[scene_id]

            if self._story_dir is not None:
                return self._load_scene_from_file(scene_id)

            legacy_story = self._load_legacy_story()
            scene_data = legacy_story.get(scene_id)
            if scene_data is None:
                raise StoryLoaderError(f'Scene "{scene_id}" not found in legacy story file')

            if not isinstance(scene_data, dict):
                raise StoryLoaderError(f'Scene "{scene_id}" must be an object')

            scene_data.setdefault('id', scene_id)
            self._cache_scene(scene_id, scene_data)
            return scene_data

    def load_all_scenes(self):
        if self._story_dir is None:
            self._load_legacy_story()
            return

        for scene_id in self._scene_index.keys():
            if scene_id not in self._cache:
                self._load_scene_from_file(scene_id)

    def validate_scene_links(self):
        all_scene_ids = set(self._scene_index.keys())
        if self._legacy_file is not None:
            all_scene_ids = set(self._load_legacy_story().keys())

        for scene_id in list(all_scene_ids):
            scene = self.get_scene(scene_id)
            for choice in scene.get('choices', []):
                next_scene = choice.get('next_scene')
                if next_scene and next_scene not in all_scene_ids:
                    raise StoryLoaderError(
                        f'Missing scene link: scene "{scene_id}" references "{next_scene}" '
                        f'but that scene does not exist'
                    )

    def scene_ids(self):
        if self._story_dir is not None:
            return list(self._scene_index.keys())
        return list(self._load_legacy_story().keys())
