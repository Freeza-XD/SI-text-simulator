import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LEGACY_STORY_FILE = BASE_DIR / 'stories' / 'tobirama.json'
TARGET_FOLDER = BASE_DIR / 'stories' / 'tobirama'


def split_legacy_story():
    if not LEGACY_STORY_FILE.exists():
        raise FileNotFoundError(f'Legacy story file not found: {LEGACY_STORY_FILE}')

    TARGET_FOLDER.mkdir(parents=True, exist_ok=True)

    with LEGACY_STORY_FILE.open(encoding='utf-8') as source:
        story = json.load(source)

    if not isinstance(story, dict):
        raise ValueError('Legacy story file must contain a JSON object mapping scene IDs to scene bodies.')

    for scene_id, scene_body in story.items():
        if not isinstance(scene_body, dict):
            raise ValueError(f'Scene "{scene_id}" must be a JSON object.')

        target_path = TARGET_FOLDER / f'{scene_id}.json'
        with target_path.open('w', encoding='utf-8') as out:
            json.dump(scene_body, out, indent=2, ensure_ascii=False)

    print(f'Wrote {len(story)} scene files to {TARGET_FOLDER}')


if __name__ == '__main__':
    split_legacy_story()
