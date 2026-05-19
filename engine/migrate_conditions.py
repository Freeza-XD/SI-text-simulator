import json
from pathlib import Path
import re

CONDITION_PATTERN = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|==|!=|>|<)\s*(-?\d+)\s*$')

BASE_DIR = Path(__file__).resolve().parent
STORY_PATH = BASE_DIR / 'stories' / 'tobirama.json'


def convert_condition(condition):
    if isinstance(condition, dict):
        return condition
    if not isinstance(condition, str):
        return None

    match = CONDITION_PATTERN.match(condition)
    if not match:
        return None

    stat, operator, value = match.groups()
    return {
        'stat': stat,
        'operator': operator,
        'value': int(value)
    }


if __name__ == '__main__':
    with STORY_PATH.open(encoding='utf-8') as f:
        story = json.load(f)

    changed = False
    for scene_id, scene_data in story.items():
        for choice in scene_data.get('choices', []):
            condition = choice.get('condition')
            if condition and isinstance(condition, str):
                new_condition = convert_condition(condition)
                if new_condition is not None:
                    choice['condition'] = new_condition
                    changed = True

    if changed:
        with STORY_PATH.open('w', encoding='utf-8') as f:
            json.dump(story, f, indent=2, ensure_ascii=False)
        print(f'Updated old string conditions to structured objects in {STORY_PATH}')
    else:
        print('No string conditions found to migrate.')
