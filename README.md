# Scholardew Valley

Scholardew Valley is a paper-reading game built on top of the open-source Pydew Valley farming prototype. You walk around a small farm to collect paper artifacts, answer question prompts graded by an LLM, keep a notebook, and maintain daily tasks for in-game rewards.

## Features

- Arrow-key avatar movement in a Stardew-like world
- Collectible knowledge artifacts with 10-question paper missions
- LLM grader
- Artifact chest with collected items and response history
- Daily task desk with persistent tasks, `+1 Strength`, and a Strawberry inventory reward for daily completion
- Player notebook for durable self-knowledge or study notes
- In-game update notice for new public releases
- Project-local default user data under `data/user/`

## Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python code/main.py
```

## macOS App Icon

To create a persistent clickable app icon, build the local macOS app bundle:

```bash
python scripts/make_macos_app.py --desktop --applications --dock
```

This creates a native `dist/Scholardew Valley.app`, copies it to your Desktop, installs a stable copy in `~/Applications`, and pins the app to your Dock. Double-click the app icon to launch the game. Rebuild it after code or dependency changes.

The macOS app stores save data in `~/Library/Application Support/Scholardew Valley`. To use an OpenAI API key with the app bundle, put a `.env` file in that folder.

## Controls

- First launch: close the welcome board with `Enter`, `Space`, `Esc`, or the `Start` button
- Arrow keys: move
- Enter near an artifact: open the mission
- Enter near the chest: open collected artifacts
- Enter near the desk, or `T`: open daily tasks
- `N`: open notebook
- `J`: open journal
- `Esc`: close open panels

## LLM Grader

Submissions require an OpenAI API key. If the key is missing or the grader is unavailable, the game shows:

```text
API key unavailable: add API key first
```

To enable grading, copy the example file:

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

On a fresh save, a wooden welcome board appears once with setup instructions. After it is dismissed, the game records that in the local player state and does not show it again for that save.

On launch, the game also checks `latest.json` on GitHub. If that file reports a newer version than the local app, the game shows a wooden update board with a GitHub link. Dismissing the board suppresses that specific version only; the next newer version can notify the player again.

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
SCHOLARDEW_UPDATE_CHECK=1
SCHOLARDEW_UPDATE_URL=https://raw.githubusercontent.com/bethyini/scholardew-valley/main/latest.json
```

To disable update checks, set `SCHOLARDEW_UPDATE_CHECK=0`.

## Publishing Updates

When publishing a new version:

1. Update `APP_VERSION` in `code/settings.py`.
2. Update `latest.json` with the same version, a short message, and a GitHub release or download URL.
3. Commit and push the change.
4. Build the app bundle:

```bash
python scripts/make_macos_app.py --desktop --applications --dock
```

Users on older versions will see the in-game update board the next time they launch the game with internet access.

## Reward Scale

Rewards use fixed tiers rather than per-question formulas:

- Field-note artifact: `25 XP` and `10g`
- Full paper mission: `100 XP` and `50g`

One full paper mission is one clean field-level step because field levels are spaced every `100 XP`.

## Tailoring Interests

The public default starts with three paper missions: one BCI paper, one computational neuroscience paper, and one protein-design paper. The quickest way to tailor the game is to edit missions in `code/knowledge.py`. Each `Mission(...)` defines the paper/topic, prompt, facts the grader checks, reward item, field badge, XP, gold, artifact description, and optional paper questions.

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

The default missions can be replaced with any public learning domain.

## Mission Quality

A good mission has:

- 10 key facts
- 10 questions split into 5 conceptual and 5 methods questions
- A unique `key` and `reward_item`
- A short artifact description
- A procedural icon branch for both artifact views

## Credits

This project extends [Pydew Valley](https://github.com/artemn0va/pydew-valley), a Python/Pygame Stardew-style project based on the [ClearCode Pydew Valley tutorial](https://www.youtube.com/watch?v=T4IX36sP_0c). The base farming code, maps, fonts, audio, and pixel graphics are from Pydew Valley unless otherwise noted. Original assets and code remain under the upstream license included in this repository.
