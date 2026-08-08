# Knowledge Homestead

Knowledge Homestead is a desktop Pygame learning game built on top of the open-source Pydew Valley farming prototype. You walk around a small farm, open artifacts, answer question prompts, collect knowledge items, keep a notebook, and maintain daily tasks for small in-game rewards.

## Features

- Arrow-key avatar movement in a Stardew-like world
- Collectible knowledge artifacts with 10-question paper missions
- Local keyword grader with optional OpenAI semantic grader
- Artifact chest with collected items and response history
- Daily task desk with persistent tasks and a strawberry reward
- Player notebook for durable self-knowledge or study notes
- Project-local default user data under `data/user/`

## Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python code/main.py
```

## Controls

- Arrow keys: move
- Enter near an artifact: open the mission
- Enter near the chest: open collected artifacts
- Enter near the desk, or `T`: open daily tasks
- `N`: open notebook
- `J`: open journal
- `Esc`: close open panels

## LLM Grader

To enable live semantic grading with an LLM, copy the example file:

```bash
cp .env.example .env
```

Then edit `.env` and paste your own key:

```bash
OPENAI_API_KEY=sk-...
OPENAI_GRADER_MODEL=gpt-4o-mini
```

Restart the game after changing `.env`. Never commit `.env`.

## User Data

The public repo is reset: it ships with no completed missions, no notebook entries, no task history, no downloaded papers, and no player save state.

By default, new player data is generated locally in:

```text
data/user/
```

This folder is ignored except for `data/user/.gitkeep`, so each player gets a private local save.

You can override paths with environment variables:

```bash
KNOWLEDGE_GAME_DATA_DIR=/path/to/private/save-data
KNOWLEDGE_GAME_NOTEBOOK_PATH=/path/to/notebook.md
KNOWLEDGE_GAME_TASKS_PATH=/path/to/daily-tasks.md
KNOWLEDGE_GAME_APP_NAME="My Learning Game"
KNOWLEDGE_GAME_NOTEBOOK_TITLE="Research Notebook"
KNOWLEDGE_GAME_NOTEBOOK_HEADING="My Profile"
```

## Tailoring Interests

The quickest way to tailor the game is to edit missions in `code/knowledge.py`. Each `Mission(...)` defines the paper/topic, prompt, facts the grader checks, reward item, field badge, XP, gold, artifact description, and optional paper questions.

For a new interest area:

1. Copy an existing `Mission(...)`.
2. Change `key`, `title`, `source`, `prompt`, `reward_item`, `reward_name`, and `badge`.
3. Add 10 `KeyFact(...)` entries with semantic labels and keyword fallbacks.
4. Add 10 `PaperQuestion(...)` entries: 5 `Conceptual` and 5 `Methods`.
5. Add a procedural icon branch for the new `reward_item` in both icon drawing functions.
6. Run:

```bash
python scripts/check_public_release.py
python -m py_compile code/*.py
```

The existing missions skew toward BCI, computational neuroscience, neuroAI, protein design, ecology, and animals, but they are ordinary data entries and can be replaced with any public learning domain.

## Mission Quality

A good mission has:

- 10 key facts
- 10 questions split into 5 conceptual and 5 methods questions
- A unique `key` and `reward_item`
- A short artifact description
- A procedural icon branch for both artifact views

Do not commit copyrighted PDFs or private notes. Link to legal public sources instead.

## Public Release Checks

Before pushing a fork, run:

```bash
python scripts/check_public_release.py
git status --short --ignored
```

The release checker scans for personal paths, key-shaped OpenAI secrets, duplicate mission IDs, missing ignore rules, and malformed 10-question missions.

## Credits

This project extends [Pydew Valley](https://github.com/artemn0va/pydew-valley), a Python/Pygame Stardew-style project based on the [ClearCode Pydew Valley tutorial](https://www.youtube.com/watch?v=T4IX36sP_0c). The base farming code, maps, fonts, audio, and pixel graphics are from Pydew Valley unless otherwise noted. Original assets and code remain under the upstream license included in this repository.
