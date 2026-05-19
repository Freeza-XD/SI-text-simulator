import json
import re
from operator import eq, ge, gt, le, lt, ne
from pathlib import Path

from flask import Flask, render_template, request, session, redirect, url_for

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'

# Load story
BASE_DIR = Path(__file__).resolve().parent
STORY_PATH = BASE_DIR / 'stories' / 'tobirama.json'

with STORY_PATH.open(encoding='utf-8') as f:
    STORY = json.load(f)

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


def evaluate_simple_condition(condition, stats):
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


def evaluate_condition(condition, stats):
    """Evaluate a condition object or parse a legacy string.

    Supports:
      - {'stat': 'honor', 'operator': '>', 'value': 70}
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
            return evaluate_simple_condition(condition, stats)

        if 'all' in condition:
            return all(evaluate_condition(sub_condition, stats) for sub_condition in condition['all'])

        if 'any' in condition:
            return any(evaluate_condition(sub_condition, stats) for sub_condition in condition['any'])

        if 'not' in condition:
            return not evaluate_condition(condition['not'], stats)

    return False


@app.route('/', methods=['GET', 'POST'])
def game():
    # Initialize stats in session
    if 'stats' not in session:
        session['stats'] = DEFAULT_STATS.copy()
    if 'current_scene' not in session:
        session['current_scene'] = 'intro'

    if request.method == 'POST':
        choice_index = int(request.form['choice'])
        current_choices = [c for c in STORY[session['current_scene']].get('choices', [])
                          if evaluate_condition(c.get('condition'), session['stats'])]

        selected_choice = current_choices[choice_index]

        # Apply effects to stats
        if 'effects' in selected_choice:
            for stat, modifier in selected_choice['effects'].items():
                session['stats'][stat] = max(0, min(100, session['stats'][stat] + modifier))

        # Move to next scene
        session['current_scene'] = selected_choice['next_scene']
        session.modified = True

    # Get current scene and filter choices by condition
    current_scene_data = STORY[session['current_scene']]
    available_choices = [c for c in current_scene_data.get('choices', [])
                         if evaluate_condition(c.get('condition'), session['stats'])]

    return render_template('game.html',
                           scene=current_scene_data,
                           choices=available_choices,
                           stats=session['stats'])


@app.route('/reset', methods=['GET'])
def reset_game():
    session.clear()
    return redirect(url_for('game'))


if __name__ == '__main__':
    app.run(debug=True)
