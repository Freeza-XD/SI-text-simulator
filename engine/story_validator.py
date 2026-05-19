import argparse
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

VALID_OPERATORS = {'>', '<', '>=', '<=', '==', '!='}

SCENE_CONDITION_KEYS = {'stat', 'operator', 'value', 'flag', 'all', 'any', 'not'}
DEFAULT_START_SCENE = 'intro'


@dataclass
class ValidationIssue:
    severity: str
    story_path: Path
    scene_id: Optional[str]
    message: str
    suggestion: Optional[str] = None

    def format(self) -> str:
        location = f"[{self.story_path.name}]"
        if self.scene_id:
            location += f" scene='{self.scene_id}'"
        text = f"{self.severity}: {location} - {self.message}"
        if self.suggestion:
            text += f"\n  Suggestion: {self.suggestion}"
        return text


class StoryDocument:
    def __init__(self, story_path: Path):
        self.story_path = story_path
        self.scenes: Dict[str, Dict[str, Any]] = {}
        self.issues: List[ValidationIssue] = []
        self.start_scene: Optional[str] = None
        self._load_story()

    def _load_story(self):
        if self.story_path.is_dir():
            self._load_scene_directory()
        elif self.story_path.is_file():
            self._load_legacy_story_file()
        else:
            raise FileNotFoundError(f"Story path not found: {self.story_path}")

    def _load_scene_directory(self):
        scene_paths = sorted(self.story_path.glob('*.json'))
        if not scene_paths:
            raise ValueError(f"No scene files found in story directory: {self.story_path}")

        for path in scene_paths:
            scene_id = path.stem
            if scene_id in self.scenes:
                self.issues.append(
                    ValidationIssue(
                        'ERROR',
                        self.story_path,
                        scene_id,
                        f'Duplicate scene ID loaded from {path.name}',
                        'Rename the file so there is exactly one file per scene ID.',
                    )
                )
                continue

            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

            if not isinstance(data, dict):
                raise ValueError(f"Scene file {path} must contain a JSON object.")

            self.scenes[scene_id] = data

        self.start_scene = self._resolve_start_scene()

    def _load_legacy_story_file(self):
        try:
            raw = self.story_path.read_text(encoding='utf-8')
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {self.story_path}: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"Story file {self.story_path} must contain a JSON object.")

        for scene_id, scene_body in data.items():
            if scene_id in self.scenes:
                self.issues.append(
                    ValidationIssue(
                        'ERROR',
                        self.story_path,
                        scene_id,
                        'Duplicate scene ID in legacy JSON file.',
                        'Remove or rename duplicate keys in the JSON object.',
                    )
                )
                continue

            if not isinstance(scene_body, dict):
                self.issues.append(
                    ValidationIssue(
                        'ERROR',
                        self.story_path,
                        scene_id,
                        'Scene body must be a JSON object.',
                        'Ensure each scene value is a JSON object with scene data.',
                    )
                )
                continue

            self.scenes[scene_id] = scene_body

        self.start_scene = self._resolve_start_scene()

    def _resolve_start_scene(self) -> Optional[str]:
        if DEFAULT_START_SCENE in self.scenes:
            return DEFAULT_START_SCENE
        if self.scenes:
            return next(iter(self.scenes.keys()))
        return None

    def scene_ids(self) -> List[str]:
        return list(self.scenes.keys())

    def get_scene(self, scene_id: str) -> Dict[str, Any]:
        return self.scenes[scene_id]

    def is_folder_story(self) -> bool:
        return self.story_path.is_dir()


class StoryRule:
    def validate(self, story: StoryDocument) -> List[ValidationIssue]:
        raise NotImplementedError()


class DuplicateSceneIdRule(StoryRule):
    def validate(self, story: StoryDocument) -> List[ValidationIssue]:
        return story.issues


class NextSceneReferenceRule(StoryRule):
    def validate(self, story: StoryDocument) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        scene_ids = set(story.scene_ids())

        for scene_id, scene in story.scenes.items():
            for index, choice in enumerate(scene.get('choices', []) if isinstance(scene.get('choices', []), list) else []):
                next_scene = choice.get('next_scene')
                if next_scene and next_scene not in scene_ids:
                    issues.append(
                        ValidationIssue(
                            'ERROR',
                            story.story_path,
                            scene_id,
                            f'Choice {index} references missing next_scene "{next_scene}".',
                            'Fix the next_scene ID or remove the broken choice.',
                        )
                    )
        return issues


class UnreachableSceneRule(StoryRule):
    def validate(self, story: StoryDocument) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        if story.start_scene is None:
            issues.append(
                ValidationIssue(
                    'WARNING',
                    story.story_path,
                    None,
                    'No start scene could be resolved.',
                    f'Add a scene named "{DEFAULT_START_SCENE}" or configure a story-level start scene.',
                )
            )
            return issues

        graph = self._build_graph(story)
        reachable = self._collect_reachable(scene_id=story.start_scene, graph=graph)

        for scene_id in story.scene_ids():
            if scene_id not in reachable:
                issues.append(
                    ValidationIssue(
                        'WARNING',
                        story.story_path,
                        scene_id,
                        'Scene is unreachable from the start scene.',
                        'Remove the scene or add a valid link from an active scene.',
                    )
                )
        return issues

    @staticmethod
    def _build_graph(story: StoryDocument) -> Dict[str, List[str]]:
        graph: Dict[str, List[str]] = {scene_id: [] for scene_id in story.scene_ids()}
        for scene_id, scene in story.scenes.items():
            for choice in scene.get('choices', []) if isinstance(scene.get('choices', []), list) else []:
                next_scene = choice.get('next_scene')
                if next_scene:
                    graph[scene_id].append(next_scene)
        return graph

    @staticmethod
    def _collect_reachable(scene_id: str, graph: Dict[str, List[str]]) -> Set[str]:
        visited: Set[str] = set()
        queue = deque([scene_id])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for neighbor in graph.get(current, []):
                if neighbor not in visited:
                    queue.append(neighbor)
        return visited


class InfiniteLoopRule(StoryRule):
    def validate(self, story: StoryDocument) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        graph = self._build_graph(story)
        sccs = self._tarjan_scc(graph)

        for scc in sccs:
            if len(scc) == 1:
                node = next(iter(scc))
                if node not in graph.get(node, []):
                    continue
            if not self._has_exit_edge(scc, graph):
                issues.append(
                    ValidationIssue(
                        'WARNING',
                        story.story_path,
                        ','.join(sorted(scc)),
                        'Detected a strongly connected cycle with no exit path.',
                        'Review this cycle and add a terminating link or an escape condition.',
                    )
                )
        return issues

    @staticmethod
    def _build_graph(story: StoryDocument) -> Dict[str, List[str]]:
        graph: Dict[str, List[str]] = {scene_id: [] for scene_id in story.scene_ids()}
        for scene_id, scene in story.scenes.items():
            for choice in scene.get('choices', []) if isinstance(scene.get('choices', []), list) else []:
                next_scene = choice.get('next_scene')
                if next_scene:
                    graph[scene_id].append(next_scene)
        return graph

    @staticmethod
    def _tarjan_scc(graph: Dict[str, List[str]]) -> List[Set[str]]:
        index = 0
        stack: List[str] = []
        indices: Dict[str, int] = {}
        lowlink: Dict[str, int] = {}
        on_stack: Set[str] = set()
        result: List[Set[str]] = []

        def strongconnect(node: str):
            nonlocal index
            indices[node] = index
            lowlink[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in indices:
                    strongconnect(neighbor)
                    lowlink[node] = min(lowlink[node], lowlink[neighbor])
                elif neighbor in on_stack:
                    lowlink[node] = min(lowlink[node], indices[neighbor])

            if lowlink[node] == indices[node]:
                component: Set[str] = set()
                while stack:
                    w = stack.pop()
                    on_stack.remove(w)
                    component.add(w)
                    if w == node:
                        break
                result.append(component)

        for node in graph:
            if node not in indices:
                strongconnect(node)

        return result

    @staticmethod
    def _has_exit_edge(component: Set[str], graph: Dict[str, List[str]]) -> bool:
        for node in component:
            for neighbor in graph.get(node, []):
                if neighbor not in component:
                    return True
        return False


class ConditionFormatRule(StoryRule):
    def validate(self, story: StoryDocument) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for scene_id, scene in story.scenes.items():
            for index, choice in enumerate(scene.get('choices', []) if isinstance(scene.get('choices', []), list) else []):
                condition = choice.get('condition')
                if condition is None:
                    continue
                issue = self._validate_condition(condition, story.story_path, scene_id, index)
                if issue:
                    issues.append(issue)
        return issues

    def _validate_condition(self, condition: Any, story_path: Path, scene_id: str, choice_index: int) -> Optional[ValidationIssue]:
        if isinstance(condition, str):
            if not self._is_valid_legacy_condition(condition):
                return ValidationIssue(
                    'ERROR',
                    story_path,
                    scene_id,
                    f'Invalid legacy condition string on choice {choice_index}: "{condition}".',
                    'Use a structured condition object or standard comparison expression.',
                )
            return None

        if not isinstance(condition, dict):
            return ValidationIssue(
                'ERROR',
                story_path,
                scene_id,
                f'Condition on choice {choice_index} must be a string or object.',
                'Use a structured condition object with keys like stat, flag, all, any, or not.',
            )

        if 'stat' in condition:
            return self._validate_stat_condition(condition, story_path, scene_id, choice_index)
        if 'flag' in condition:
            return self._validate_flag_condition(condition, story_path, scene_id, choice_index)
        if 'all' in condition or 'any' in condition:
            return self._validate_composite_condition(condition, story_path, scene_id, choice_index)
        if 'not' in condition:
            return self._validate_not_condition(condition, story_path, scene_id, choice_index)

        return ValidationIssue(
            'ERROR',
            story_path,
            scene_id,
            f'Condition on choice {choice_index} is missing a supported key ({SCENE_CONDITION_KEYS}).',
            'Use one of: stat, flag, all, any, not.',
        )

    @staticmethod
    def _is_valid_legacy_condition(expression: str) -> bool:
        pattern = r'^\s*[A-Za-z_][A-Za-z0-9_]*\s*(>=|<=|==|!=|>|<)\s*-?\d+\s*$'
        return bool(__import__('re').match(pattern, expression))

    def _validate_stat_condition(self, condition, story_path, scene_id, choice_index):
        operator = condition.get('operator')
        value = condition.get('value')
        if operator not in VALID_OPERATORS:
            return ValidationIssue(
                'ERROR',
                story_path,
                scene_id,
                f'Invalid operator in stat condition on choice {choice_index}: {operator!r}.',
                f'Use one of {sorted(VALID_OPERATORS)}.',
            )
        if not isinstance(value, (int, float)):
            return ValidationIssue(
                'ERROR',
                story_path,
                scene_id,
                f'Invalid value type in stat condition on choice {choice_index}: {type(value).__name__}.',
                'Use a numeric value for stat comparisons.',
            )
        return None

    def _validate_flag_condition(self, condition, story_path, scene_id, choice_index):
        if 'flag' not in condition:
            return ValidationIssue(
                'ERROR',
                story_path,
                scene_id,
                f'Flag condition on choice {choice_index} is missing "flag" key.',
                'Add a "flag" entry with the flag name.',
            )
        if 'operator' in condition and condition['operator'] not in VALID_OPERATORS:
            return ValidationIssue(
                'ERROR',
                story_path,
                scene_id,
                f'Invalid operator in flag condition on choice {choice_index}: {condition.get("operator")!r}.',
                f'Use one of {sorted(VALID_OPERATORS)} or omit operator for truthy checks.',
            )
        if 'operator' in condition and 'value' not in condition:
            return ValidationIssue(
                'ERROR',
                story_path,
                scene_id,
                f'Flag condition on choice {choice_index} has operator but no value.',
                'Add a boolean or numeric value to compare against.',
            )
        return None

    def _validate_composite_condition(self, condition, story_path, scene_id, choice_index):
        if 'all' in condition and not isinstance(condition['all'], list):
            return ValidationIssue(
                'ERROR',
                story_path,
                scene_id,
                f'The "all" condition on choice {choice_index} must be a list.',
                'Use a list of sub-conditions.',
            )
        if 'any' in condition and not isinstance(condition['any'], list):
            return ValidationIssue(
                'ERROR',
                story_path,
                scene_id,
                f'The "any" condition on choice {choice_index} must be a list.',
                'Use a list of sub-conditions.',
            )
        subconditions = condition.get('all') or condition.get('any')
        for index, sub in enumerate(subconditions or []):
            issue = self._validate_condition(sub, story_path, scene_id, choice_index)
            if issue:
                return issue
        return None

    def _validate_not_condition(self, condition, story_path, scene_id, choice_index):
        if 'not' not in condition:
            return ValidationIssue(
                'ERROR',
                story_path,
                scene_id,
                f'The "not" condition on choice {choice_index} must contain a sub-condition.',
                'Use {"not": { ... }} with a valid nested condition object.',
            )
        return self._validate_condition(condition['not'], story_path, scene_id, choice_index)


class EffectStructureRule(StoryRule):
    def validate(self, story: StoryDocument) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for scene_id, scene in story.scenes.items():
            effects = scene.get('effects')
            if effects is None:
                continue
            if not isinstance(effects, dict):
                issues.append(
                    ValidationIssue(
                        'ERROR',
                        story.story_path,
                        scene_id,
                        'Effects must be a JSON object mapped by stat name.',
                        'Use {"strength": 10, "honor": -5}.',
                    )
                )
                continue
            for key, value in effects.items():
                if not isinstance(key, str):
                    issues.append(
                        ValidationIssue(
                            'ERROR',
                            story.story_path,
                            scene_id,
                            f'Effect key must be a string, got {type(key).__name__}.',
                            'Use stat names as string keys.',
                        )
                    )
                if not isinstance(value, (int, float)):
                    issues.append(
                        ValidationIssue(
                            'ERROR',
                            story.story_path,
                            scene_id,
                            f'Effect value for "{key}" must be numeric, got {type(value).__name__}.',
                            'Use an integer or float effect modifier.',
                        )
                    )
        return issues


class StoryValidator:
    def __init__(self, rules: Optional[List[StoryRule]] = None):
        self.rules = rules or [
            DuplicateSceneIdRule(),
            NextSceneReferenceRule(),
            UnreachableSceneRule(),
            InfiniteLoopRule(),
            ConditionFormatRule(),
            EffectStructureRule(),
        ]

    def validate(self, story: StoryDocument) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for rule in self.rules:
            issues.extend(rule.validate(story))
        return issues


class StoryDiscovery:
    def __init__(self, stories_root: Path):
        self.stories_root = stories_root

    def discover(self) -> List[Path]:
        items: List[Path] = []
        if not self.stories_root.exists():
            raise FileNotFoundError(f'Stories root not found: {self.stories_root}')

        for child in sorted(self.stories_root.iterdir()):
            if child.is_dir():
                if any(child.glob('*.json')):
                    items.append(child)
            elif child.is_file() and child.suffix.lower() == '.json':
                items.append(child)
        return items


def format_summary(issues: List[ValidationIssue]) -> str:
    if not issues:
        return 'No validation issues found. Story structure looks good.'
    lines = [f'Total issues: {len(issues)}']
    for issue in issues:
        lines.append(issue.format())
    return '\n\n'.join(lines)


def run_validator(stories_root: Path, story_filter: Optional[str] = None) -> int:
    discovery = StoryDiscovery(stories_root)
    story_paths = discovery.discover()
    if story_filter:
        story_paths = [p for p in story_paths if story_filter in p.name]

    if not story_paths:
        print(f'No stories found in {stories_root}')
        return 1

    validator = StoryValidator()
    all_issues: List[ValidationIssue] = []

    for story_path in story_paths:
        print(f'Validating story: {story_path}')
        try:
            story = StoryDocument(story_path)
        except Exception as exc:
            print(f'ERROR: Failed to load story {story_path}: {exc}')
            all_issues.append(
                ValidationIssue('ERROR', story_path, None, f'Failed to load story: {exc}')
            )
            continue

        story_issues = validator.validate(story)
        all_issues.extend(story_issues)
        print(f'  scenes: {len(story.scene_ids())}, start_scene: {story.start_scene}')
        print(f'  issues: {len(story_issues)}\n')

    print(format_summary(all_issues))
    return 1 if any(i.severity == 'ERROR' for i in all_issues) else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Validate narrative story folders.')
    parser.add_argument('--stories-root', type=Path, default=Path('stories'), help='Root folder containing story folders or JSON files.')
    parser.add_argument('--story', type=str, help='Optional story name filter.')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    exit_code = run_validator(args.stories_root, args.story)
    raise SystemExit(exit_code)


if __name__ == '__main__':
    main()
