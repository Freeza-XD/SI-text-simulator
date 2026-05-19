import json
import re
from operator import eq, ge, gt, le, lt, ne
from pathlib import Path

from flask import Flask, render_template, request, session, redirect, url_for

from engine.story_loader import StoryLoader, StoryLoaderError
from engine.effects import process_effects

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR

app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / 'templates'),
    static_folder=str(PROJECT_ROOT / 'static'),
)
app.secret_key = 'no-Ls-for-unown-w'

STORIES_DIR = PROJECT_ROOT / 'stories'
STORY_SLUG = 'tobirama'

story_loader = StoryLoader(STORIES_DIR, STORY_SLUG, cache_max_size=2000)

# Default player stats
DEFAULT_STATS = {
    'honor': 50,
    'strength': 50,
    'intellect': 50,
    'compassion': 50,
    'ambition': 50
}

CONDITION_OPERATORS = {
    '>': gt,
    '<': lt,
    '>=': ge,
    '<=': le,
    '==': eq,
    '!=': ne,
}

COMPARISON_PATTERN = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|==|!=|>|<)\s*(-?\d+)\s*$')


def init_session_state():
    """Ensure stats, flags, and current scene exist in the user session."""
    if 'stats' not in session:
        session['stats'] = DEFAULT_STATS.copy()
    if 'flags' not in session:
        session['flags'] = {}
    if 'inventory' not in session:
        session['inventory'] = {}
    if 'relationships' not in session:
        session['relationships'] = {}
    if 'current_scene' not in session:
        session['current_scene'] = 'intro'


def set_flag(flag_name):
    """Set a persistent narrative flag."""
    flags = session.setdefault('flags', {})
    flags[flag_name] = True
    session.modified = True


def remove_flag(flag_name):
    """Remove a narrative flag."""
    flags = session.setdefault('flags', {})
    if flag_name in flags:
        flags.pop(flag_name)
        session.modified = True


def check_flag(flag_name):
    """Check whether a narrative flag is set."""
    return session.get('flags', {}).get(flag_name, False)


def apply_flag_changes(flag_spec, flags):
    """Apply flag changes defined in a scene or choice."""
    if not isinstance(flag_spec, dict):
        return

    for flag_name in flag_spec.get('set', []):
        flags[flag_name] = True

    for flag_name in flag_spec.get('remove', []):
        flags.pop(flag_name, None)

    for flag_name, value in flag_spec.get('values', {}).items():
        flags[flag_name] = value

    session.modified = True


def parse_condition_string(condition):
    """Convert legacy string conditions like "honor > 50" into structured objects."""
    if not isinstance(condition, str):
        return None

    match = COMPARISON_PATTERN.match(condition)
    if not match:
        return None

    stat, operator_symbol, value = match.groups()
    return {
        'stat': stat,
        'operator': operator_symbol,
        'value': int(value)
    }


def evaluate_stat_condition(condition, stats):
    """Evaluate one stat comparison condition."""
    if not isinstance(condition, dict):
        return False

    stat = condition.get('stat')
    operator_symbol = condition.get('operator')
    target_value = condition.get('value')

    if stat is None or operator_symbol not in CONDITION_OPERATORS or target_value is None:
        return False

    stat_value = stats.get(stat)
    if stat_value is None:
        return False

    return CONDITION_OPERATORS[operator_symbol](stat_value, target_value)


def evaluate_flag_condition(condition, flags):
    """Evaluate one flag condition."""
    if not isinstance(condition, dict):
        return False

    flag_name = condition.get('flag')
    if not flag_name:
        return False

    flag_value = flags.get(flag_name, False)
    operator_symbol = condition.get('operator')

    if operator_symbol is None:
        return bool(flag_value)

    if operator_symbol not in CONDITION_OPERATORS:
        return False

    target_value = condition.get('value')
    if target_value is None:
        return False

    return CONDITION_OPERATORS[operator_symbol](flag_value, target_value)


def evaluate_condition(condition, stats, flags):
    """Evaluate a condition object or parse a legacy string.

    Supports:
      - {'stat': 'honor', 'operator': '>', 'value': 70}
      - {'flag': 'izuna_saved'}
      - {'flag': 'izuna_saved', 'operator': '==', 'value': true}
      - {'all': [ ... ]}
      - {'any': [ ... ]}
      - {'not': {...}}
    """
    if not condition:
        return True

    if isinstance(condition, str):
        condition = parse_condition_string(condition)
        if condition is None:
            return False

    if isinstance(condition, dict):
        if 'stat' in condition:
            return evaluate_stat_condition(condition, stats)

        if 'flag' in condition:
            return evaluate_flag_condition(condition, flags)

        if 'all' in condition:
            return all(evaluate_condition(sub_condition, stats, flags)
                       for sub_condition in condition['all'])

        if 'any' in condition:
            return any(evaluate_condition(sub_condition, stats, flags)
                       for sub_condition in condition['any'])

        if 'not' in condition:
            return not evaluate_condition(condition['not'], stats, flags)

    return False


@app.route('/', methods=['GET', 'POST'])
def game():
    init_session_state()

    if request.method == 'POST':
        choice_index = int(request.form['choice'])
        current_scene_data = story_loader.get_scene(session['current_scene'])
        current_choices = [c for c in current_scene_data.get('choices', [])
                          if evaluate_condition(c.get('condition'), session['stats'], session['flags'])]

        selected_choice = current_choices[choice_index]

        # Apply effects (supports legacy dicts and new list format)
        process_effects(selected_choice.get('effects'))

        # Apply flag changes from the selected choice
        apply_flag_changes(selected_choice.get('flags', {}), session['flags'])

        # Move to next scene
        session['current_scene'] = selected_choice['next_scene']
        session.modified = True

    # Get current scene, apply scene-level flags, and filter choices by condition
    current_scene_data = story_loader.get_scene(session['current_scene'])
    apply_flag_changes(current_scene_data.get('flags', {}), session['flags'])
    available_choices = [c for c in current_scene_data.get('choices', [])
                         if evaluate_condition(c.get('condition'), session['stats'], session['flags'])]

    return render_template('game.html',
                           scene=current_scene_data,
                           choices=available_choices,
                           stats=session['stats'],
                           flags=session['flags'],
                           inventory=session['inventory'],
                           relationships=session['relationships'])


@app.route('/reset', methods=['GET'])
def reset_game():
    session.clear()
    return redirect(url_for('game'))


if __name__ == '__main__':
    app.run(debug=True)
