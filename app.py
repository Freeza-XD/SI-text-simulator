from flask import Flask, render_template, request, session, redirect, url_for
import json

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'

# Load story
with open('Stories/tobirama.json', 'r') as f:
    STORY = json.load(f)

# Default player stats
DEFAULT_STATS = {
    'honor': 50,
    'strength': 50,
    'intellect': 50,
    'compassion': 50,
    'ambition': 50
}

def evaluate_condition(condition, stats):
    """Evaluate if a choice should be shown based on stats"""
    if not condition:
        return True
    
    try:
        # Replace stat names with their values
        expression = condition
        for stat, value in stats.items():
            expression = expression.replace(stat, str(value))
        # Evaluate the expression safely
        return eval(expression)
    except:
        return True

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