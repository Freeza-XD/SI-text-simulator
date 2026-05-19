from typing import Any, Dict, List
from flask import session


def _ensure_inventory():
    if 'inventory' not in session:
        session['inventory'] = {}


def _ensure_relationships():
    if 'relationships' not in session:
        session['relationships'] = {}


def _apply_stat_effect(target: str, value: float, mode: str = 'delta') -> None:
    stats = session.setdefault('stats', {})
    current = stats.get(target, 0)
    if mode == 'set':
        stats[target] = int(max(0, min(100, value)))
    else:
        # delta
        stats[target] = int(max(0, min(100, current + value)))
    session.modified = True


def _apply_flag_effect(target: str, value: Any) -> None:
    flags = session.setdefault('flags', {})
    if value:
        flags[target] = True
    else:
        flags.pop(target, None)
    session.modified = True


def _apply_inventory_effect(action: str, item: str, quantity: int = 1) -> None:
    _ensure_inventory()
    inv = session['inventory']
    if action == 'add':
        inv[item] = inv.get(item, 0) + quantity
    elif action == 'remove':
        if item in inv:
            inv[item] = max(0, inv[item] - quantity)
            if inv[item] == 0:
                inv.pop(item)
    elif action == 'set':
        if quantity <= 0:
            inv.pop(item, None)
        else:
            inv[item] = quantity
    session.modified = True


def _apply_relationship_effect(target: str, value: float, mode: str = 'delta') -> None:
    _ensure_relationships()
    rel = session['relationships']
    current = rel.get(target, 0)
    if mode == 'set':
        rel[target] = int(value)
    else:
        rel[target] = int(current + value)
    session.modified = True


def process_effects(effects: Any) -> None:
    """Process a list of effect descriptors or legacy dict.

    Supported formats:
      - Legacy: { "honor": 10, "compassion": -5 }
      - New list:
        [ {"type": "stat", "target": "honor", "value": 10},
          {"type": "flag", "target": "izuna_saved", "value": true} ]

    Each effect object may include optional keys:
      - mode: 'delta' (default) or 'set' for stats/relationships
      - for inventory: action ('add'|'remove'|'set') and quantity
    """
    if not effects:
        return

    # Legacy dict: treat keys as stat deltas
    if isinstance(effects, dict):
        for k, v in effects.items():
            try:
                delta = float(v)
            except Exception:
                continue
            _apply_stat_effect(k, delta, mode='delta')
        return

    if not isinstance(effects, list):
        return

    for eff in effects:
        if not isinstance(eff, dict):
            continue
        etype = eff.get('type')
        if etype == 'stat':
            target = eff.get('target')
            value = eff.get('value', 0)
            mode = eff.get('mode', 'delta')
            try:
                _apply_stat_effect(str(target), float(value), mode=mode)
            except Exception:
                continue
        elif etype == 'flag':
            target = eff.get('target')
            value = eff.get('value', True)
            _apply_flag_effect(str(target), value)
        elif etype == 'inventory':
            action = eff.get('action', 'add')
            item = eff.get('item')
            quantity = int(eff.get('quantity', 1))
            if item:
                _apply_inventory_effect(action, str(item), quantity)
        elif etype == 'relationship':
            target = eff.get('target')
            value = eff.get('value', 0)
            mode = eff.get('mode', 'delta')
            if target:
                _apply_relationship_effect(str(target), float(value), mode=mode)
        else:
            # unknown effect type - ignore for now
            continue
