from dataclasses import dataclass
from datetime import date, timedelta
import json
import math
import os
from queue import Empty, Queue
from threading import Thread
import urllib.error
import urllib.request
import webbrowser
from typing import Tuple

import pygame

from settings import APP_VERSION, ENV_PATH, KNOWLEDGE_STATE_PATH, LAYERS, SCREEN_HEIGHT, SCREEN_WIDTH
from support import get_path
from update_check import read_latest_update


PANEL = (244, 229, 188)
PANEL_DARK = (96, 62, 39)
PANEL_SHADOW = (45, 31, 24)
INK = (35, 25, 20)
MUTED = (92, 76, 60)
ACCENT = (152, 84, 38)
SUCCESS = (47, 111, 78)
WARNING = (155, 58, 48)
MAX_RESEARCH_HEALTH = 5
STATE_PATH = KNOWLEDGE_STATE_PATH
OPENAI_RESPONSES_URL = 'https://api.openai.com/v1/responses'
SKILL_LEVEL_XP = 100
MAX_ANSWER_CHARS = 6000
LLM_GRADER_TIMEOUT = 8
SUBMIT_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER)
SUBMIT_MODS = pygame.KMOD_CTRL | pygame.KMOD_META
API_KEY_MISSING_MESSAGE = 'API key unavailable: add API key first'
STARTER_MISSION_KEYS = (
    'neural-population-dynamics-reaching',
    'handwriting-brain-to-text',
    'rfdiffusion',
)
REWARD_TIERS = {
    'field_note': {'xp': 25, 'gold': 10},
    'paper_mission': {'xp': 100, 'gold': 50},
}


def load_env_file(path=ENV_PATH):
    if not path.exists():
        return

    try:
        lines = path.read_text().splitlines()
    except OSError:
        return

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue

        key, value = stripped.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file()


def reward_xp(_required_hits, has_questions=False):
    tier = 'paper_mission' if has_questions else 'field_note'
    return REWARD_TIERS[tier]['xp']


def reward_gold(xp):
    if xp >= REWARD_TIERS['paper_mission']['xp']:
        return REWARD_TIERS['paper_mission']['gold']
    return REWARD_TIERS['field_note']['gold']


@dataclass(frozen=True)
class KeyFact:
    label: str
    keywords: Tuple[str, ...]


@dataclass(frozen=True)
class PaperQuestion:
    category: str
    text: str


@dataclass(frozen=True)
class GradeResult:
    passed: bool
    hits: Tuple[str, ...]
    missing: Tuple[str, ...]
    response: str
    grader: str


class GraderUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Mission:
    key: str
    title: str
    source: str
    prompt: str
    key_facts: Tuple[KeyFact, ...]
    reward_item: str
    reward_name: str
    badge: str
    xp: int
    gold: int
    artifact_description: str = ''
    required_hits: int = 2
    questions: Tuple[PaperQuestion, ...] = ()


MISSION_LIBRARY = (
    Mission(
        key='candlefish',
        title='Candlefish Field Note',
        source='Mission paper: Eulachon ecology primer',
        prompt=(
            'Read the field note, then explain why candlefish are unusual and '
            'what kind of habitat cycle they depend on.'
        ),
        key_facts=(
            KeyFact('candlefish are eulachon', ('eulachon', 'oolichan', 'candlefish')),
            KeyFact('they are very oily', ('oil', 'oily', 'fat', 'grease')),
            KeyFact('they migrate from sea to rivers', ('anadromous', 'river', 'freshwater', 'spawn')),
        ),
        reward_item='candlefish',
        reward_name='Candlefish',
        badge='Ecology',
        xp=reward_xp(2),
        gold=reward_gold(reward_xp(2)),
        artifact_description=(
            'A small silver-blue fish artifact for eulachon ecology: oily, '
            'anadromous, and tied to river spawning cycles.'
        ),
    ),
    Mission(
        key='temporal-predictive-coding',
        title='Temporal Predictive Coding',
        source='Mission paper: Millidge et al., PLOS Computational Biology 2024',
        prompt=(
            'Answer the 10 paper questions. Focus on how temporal predictive '
            'coding turns dynamic sensory streams into biologically plausible '
            'prediction and learning.'
        ),
        key_facts=(
            KeyFact('addresses temporal prediction in dynamic sensory streams', ('temporal prediction', 'dynamic', 'sequence', 'sensory stream', 'time-varying')),
            KeyFact('predictive coding compares predictions with observations', ('prediction error', 'predictive coding', 'observed input', 'prediction')),
            KeyFact('uses recurrent networks for future state prediction', ('recurrent', 'future', 'one time-step', 'next step', 'state')),
            KeyFact('uses local inputs and Hebbian plasticity', ('local input', 'local inputs', 'hebbian', 'plasticity', 'biologically plausible')),
            KeyFact('approximates the Kalman filter in linear systems', ('kalman', 'filter', 'linear system', 'linear regime', 'approximation')),
            KeyFact('avoids complex matrix operations or Kalman gain computation', ('matrix inversion', 'kalman gain', 'simple computation', 'computationally cheaper')),
            KeyFact('can learn model parameters online', ('online learning', 'learn parameters', 'system parameters', 'online')),
            KeyFact('does not track posterior variance like a full Kalman filter', ('posterior variance', 'uncertainty', 'subjective posterior', 'does not track')),
            KeyFact('natural dynamic inputs yield motion-sensitive Gabor-like receptive fields', ('gabor', 'motion-sensitive', 'receptive field', 'natural moving stimuli', 'visual cortex')),
            KeyFact('generalizes to nonlinear systems', ('nonlinear', 'non-linear', 'nonlinear dynamics', 'sequence prediction')),
        ),
        reward_item='prediction_lens',
        reward_name='Prediction Lens',
        badge='Computational Neuroscience',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A prediction-error lens for computational neuroscience: dynamic '
            'sensory streams, recurrent predictive coding, Kalman-filter '
            'approximations, and motion-sensitive visual representations.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What temporal prediction problem does the paper address?'),
            PaperQuestion('Conceptual', 'How does prediction error drive inference or learning?'),
            PaperQuestion('Conceptual', 'Why is biological plausibility central here?'),
            PaperQuestion('Conceptual', 'Why compare temporal predictive coding with a Kalman filter?'),
            PaperQuestion('Conceptual', 'What do motion-sensitive receptive fields imply?'),
            PaperQuestion('Methods', 'What latent states and observations are modeled?'),
            PaperQuestion('Methods', 'How do recurrent connections support one-step-ahead prediction?'),
            PaperQuestion('Methods', 'Which local/Hebbian updates replace BPTT-like training?'),
            PaperQuestion('Methods', 'What does the model omit relative to full Kalman filtering?'),
            PaperQuestion('Methods', 'How is the nonlinear extension evaluated?'),
        ),
    ),
    Mission(
        key='neural-population-dynamics-reaching',
        title='Neural Population Dynamics',
        source='Mission paper: Churchland et al., Nature 2012',
        prompt=(
            'Answer the 10 paper questions. Focus on how motor-cortex '
            'population activity during reaching behaves like a dynamical system.'
        ),
        key_facts=(
            KeyFact('argues that motor cortex activity is better understood as population dynamics than simple parameter representation', ('population dynamics', 'dynamical system', 'movement parameters', 'representation')),
            KeyFact('finds brief quasi-oscillatory activity during non-rhythmic reaching', ('quasi-oscillatory', 'oscillatory', 'non-rhythmic', 'reaching')),
            KeyFact('uses preparatory state to set the phase and amplitude of movement-period rotations', ('preparatory state', 'phase', 'amplitude', 'movement-period')),
            KeyFact('analyzes M1 and PMd recordings from four monkeys during delayed reaching', ('m1', 'pmd', 'four monkeys', 'delayed reach', 'instructed delay')),
            KeyFact('combines 469 single-neuron recordings with simultaneous 96-electrode array recordings', ('469', 'single-neuron', '96-electrode', 'array', 'simultaneous')),
            KeyFact('uses jPCA to reveal rotational structure within the top principal components', ('jpca', 'principal component', 'pca', 'rotational structure')),
            KeyFact('rotations are consistent across reach conditions and not explained by reach curvature', ('same direction', 'consistent', 'conditions', 'curvature')),
            KeyFact('shuffle controls and model comparisons reject trivial multiphasic or kinematic explanations', ('shuffle', 'velocity model', 'complex kinematic', 'control', 'multiphasic')),
            KeyFact('EMG lacks the same rotations but can be fit by a generator model built from rotations', ('emg', 'generator model', 'muscle', 'fit', '0.97', '0.99')),
            KeyFact('quantifies rotations with a skew-symmetric dynamics matrix relating state to its derivative', ('skew-symmetric', 'm skew', 'state derivative', 'eigenvalue', 'rotation strength')),
        ),
        reward_item='jpca_spindle',
        reward_name='jPCA Spindle',
        badge='Computational Neuroscience',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A computational neuroscience artifact for motor-cortex dynamics: '
            'preparatory states, jPCA projections, state-space rotations, '
            'model controls, EMG generator fits, and dynamical-system thinking '
            'for reaching and neural decoding.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'Why does the paper argue against viewing motor cortex mainly as a representation of movement parameters?'),
            PaperQuestion('Conceptual', 'Why are rotations surprising during a non-rhythmic reach?'),
            PaperQuestion('Conceptual', 'What role does the preparatory state play in the dynamical-systems interpretation?'),
            PaperQuestion('Conceptual', 'How can simple population structure explain complex single-neuron responses?'),
            PaperQuestion('Conceptual', 'Why is this paper useful for thinking about BCI decoder design or motor-control models?'),
            PaperQuestion('Methods', 'What animals, cortical areas, recording types, and reach conditions were analyzed?'),
            PaperQuestion('Methods', 'How does jPCA differ from ordinary PCA in what it tries to reveal?'),
            PaperQuestion('Methods', 'How did the authors test whether rotations were consistent across reach conditions and not just reach curvature?'),
            PaperQuestion('Methods', 'What velocity-model, complex-kinematic-model, EMG, and shuffle controls were used?'),
            PaperQuestion('Methods', 'How were rotational dynamics quantified using state derivatives, M_skew, eigenvectors, and fast-versus-slow reach comparisons?'),
        ),
    ),
    Mission(
        key='neural-constraints-learning',
        title='Neural Constraints on Learning',
        source='Mission paper: Sadtler et al., Nature 2014',
        prompt=(
            'Answer the 10 paper questions. Focus on how closed-loop BCI '
            'perturbations reveal which neural activity patterns are learnable.'
        ),
        key_facts=(
            KeyFact('uses a closed-loop intracortical BCI learning paradigm', ('closed-loop', 'intracortical', 'bci', 'brain-computer interface')),
            KeyFact('rhesus monkeys controlled a cursor by modulating primary motor cortex activity', ('rhesus', 'monkey', 'cursor', 'primary motor cortex', 'm1')),
            KeyFact('records 85 to 91 neural units from 96-channel microelectrode arrays', ('85', '91', '96-channel', 'microelectrode', 'array')),
            KeyFact('defines an intrinsic manifold from natural low-dimensional co-modulation patterns', ('intrinsic manifold', 'low-dimensional', 'co-modulation', 'natural patterns')),
            KeyFact('uses factor analysis to map population activity into the intrinsic manifold', ('factor analysis', 'population activity', 'intrinsic manifold', 'factors')),
            KeyFact('maps intrinsic-manifold activity to cursor velocity with a Kalman-filter-style decoder', ('kalman', 'cursor velocity', 'decoder', 'kinematics')),
            KeyFact('within-manifold perturbations require new associations between existing co-modulation patterns and cursor kinematics', ('within-manifold', 'association', 'co-modulation', 'cursor kinematics')),
            KeyFact('outside-manifold perturbations require generating new co-modulation patterns', ('outside-manifold', 'new co-modulation', 'depart', 'control space')),
            KeyFact('within-manifold perturbations are learned more readily than outside-manifold perturbations', ('learned', 'more readily', 'performance recovered', 'within-manifold', 'outside-manifold')),
            KeyFact('controls examine initial impairment, control-space angles, preferred-direction changes, search space, and hand movement', ('initial impairment', 'control-space angle', 'preferred direction', 'search space', 'hand movement')),
        ),
        reward_item='intrinsic_manifold_map',
        reward_name='Intrinsic Manifold Map',
        badge='BCI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A BCI learning artifact for neural-manifold thinking: closed-loop '
            'cursor control, factor-analysis manifolds, within- and outside-'
            'manifold perturbations, Kalman-style decoding, and controls that '
            'separate learnability from task difficulty.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What is the intrinsic manifold, and why does the paper treat it as a constraint on learning?'),
            PaperQuestion('Conceptual', 'Why is a closed-loop BCI a useful way to test which neural activity patterns animals can learn?'),
            PaperQuestion('Conceptual', 'Why should within-manifold perturbations be easier than outside-manifold perturbations?'),
            PaperQuestion('Conceptual', 'What does this result imply about why some new motor skills are easier than others?'),
            PaperQuestion('Conceptual', 'How could this paper influence the design of future BCI decoders or training tasks?'),
            PaperQuestion('Methods', 'What animals, cortical area, recording hardware, and neural features were used?'),
            PaperQuestion('Methods', 'How were the intuitive BCI mapping and intrinsic manifold estimated at the start of a session?'),
            PaperQuestion('Methods', 'How were within-manifold and outside-manifold perturbations constructed, and what did each preserve or disrupt?'),
            PaperQuestion('Methods', 'How did the authors quantify learning, performance recovery, and aftereffects?'),
            PaperQuestion('Methods', 'Which control analyses ruled out simpler explanations such as different initial difficulty, control-space distance, preferred-direction changes, search-space size, or hand movements?'),
        ),
    ),
    Mission(
        key='speech-neuroprosthesis',
        title='Speech Neuroprosthesis',
        source='Mission paper: Willett et al., Nature 2023',
        prompt=(
            'Answer the 10 paper questions. Focus on how an intracortical '
            'speech BCI turns attempted speech activity into real-time text.'
        ),
        key_facts=(
            KeyFact('builds a speech BCI for restoring communication in paralysis', ('speech bci', 'speech neuroprosthesis', 'communication', 'paralysis')),
            KeyFact('records spiking activity from intracortical microelectrode arrays', ('intracortical', 'microelectrode', 'array', 'spiking')),
            KeyFact('studies a BrainGate2 participant with ALS', ('braingate', 'braingate2', 'als', 't12')),
            KeyFact('uses left area 6v recordings for decoding', ('area 6v', 'ventral premotor', 'orofacial', 'motor cortex')),
            KeyFact('decodes attempted speech into phoneme probabilities with an RNN', ('rnn', 'phoneme', 'probability', 'attempted speech')),
            KeyFact('uses a language model to infer word sequences', ('language model', 'kaldi', 'trigram', 'word sequence')),
            KeyFact('achieves low error on a 50-word vocabulary', ('50 word', '9.1', 'word error', 'wer')),
            KeyFact('demonstrates large-vocabulary decoding around 125,000 words', ('125,000', '125k', 'large vocabulary', '23.8')),
            KeyFact('decodes at roughly 62 words per minute', ('62 words per minute', '62 wpm', 'speed', 'words per minute')),
            KeyFact('finds preserved articulatory phoneme representations', ('articulatory', 'phoneme representation', 'preserved', 'vowels', 'consonants')),
        ),
        reward_item='speech_decoder',
        reward_name='Speech Decoder',
        badge='BCI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A BCI artifact for intracortical speech decoding: BrainGate2, '
            'area 6v arrays, attempted speech, phoneme RNNs, language models, '
            'large-vocabulary text output, and preserved articulatory codes.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What communication problem does the speech neuroprosthesis address?'),
            PaperQuestion('Conceptual', 'Why is attempted speech a useful control signal for a BCI?'),
            PaperQuestion('Conceptual', 'Why does large-vocabulary decoding matter more than a small fixed phrase set?'),
            PaperQuestion('Conceptual', 'What does preserved articulatory phoneme structure imply about speech motor cortex after paralysis?'),
            PaperQuestion('Conceptual', 'What are the main limitations or next engineering steps for this kind of BCI?'),
            PaperQuestion('Methods', 'Where were the arrays implanted, and which area provided useful decoding signals?'),
            PaperQuestion('Methods', 'What neural features were extracted before decoding?'),
            PaperQuestion('Methods', 'How does the RNN convert neural activity into phoneme probabilities?'),
            PaperQuestion('Methods', 'How does the language model change phoneme probabilities into text?'),
            PaperQuestion('Methods', 'How were word error rate and speaking speed evaluated across vocabulary sizes?'),
        ),
    ),
    Mission(
        key='rapid-calibrating-speech-neuroprosthesis',
        title='Rapid Speech Neuroprosthesis',
        source='Mission paper: Card et al., NEJM 2024',
        prompt=(
            'Answer the 10 paper questions. Focus on how a speech BCI can '
            'be calibrated quickly enough for naturalistic conversation.'
        ),
        key_facts=(
            KeyFact('restores conversational communication by decoding attempted speech into text', ('conversational communication', 'attempted speech', 'speech neuroprosthesis', 'brain-to-text')),
            KeyFact('studies a 45-year-old man with ALS, tetraparesis, and severe dysarthria', ('45-year-old', 'als', 'tetraparesis', 'severe dysarthria')),
            KeyFact('uses the BrainGate2 clinical trial system', ('braingate2', 'braingate', 'clinical trial', 'nct00912041')),
            KeyFact('implants four microelectrode arrays in the left precentral gyrus', ('four', 'microelectrode arrays', 'left precentral gyrus', 'precentral')),
            KeyFact('records from 256 intracortical electrodes', ('256', 'intracortical electrodes', 'recording sites', 'electrodes')),
            KeyFact('targets d6v, v6v, area 4, and area 55b speech-related regions', ('d6v', 'v6v', 'area 4', 'area 55b')),
            KeyFact('uses Copy Task and self-paced Conversation Mode', ('copy task', 'conversation mode', 'self-paced', 'unstructured')),
            KeyFact('predicts English phonemes every 80 ms and refines text with language models', ('80 ms', 'phoneme', 'language model', 'open-source language models')),
            KeyFact('achieves 99.6 percent accuracy with a 50-word vocabulary after 30 minutes of calibration', ('99.6', '50-word', '30 minutes', 'calibration')),
            KeyFact('scales to a 125,000-word vocabulary and sustains high-accuracy use for 248 hours', ('125,000', '97.5', '248', '8.4 months')),
        ),
        reward_item='rapid_speech_console',
        reward_name='Rapid Speech Console',
        badge='BCI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A BCI artifact for quickly calibrated conversational speech: four '
            'precentral-gyrus arrays, 256 intracortical electrodes, phoneme '
            'decoding every 80 ms, language-model refinement, Copy Task '
            'calibration, and long-running Conversation Mode.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'Why does rapid calibration matter for making speech BCIs clinically useful?'),
            PaperQuestion('Conceptual', 'Why can attempted speech remain a useful neural control signal even when speech muscles fail?'),
            PaperQuestion('Conceptual', 'Why is moving from a 50-word vocabulary to a 125,000-word vocabulary important?'),
            PaperQuestion('Conceptual', 'What does self-paced Conversation Mode demonstrate beyond prompted copy-task decoding?'),
            PaperQuestion('Conceptual', 'What are the main limitations or translation barriers for this system?'),
            PaperQuestion('Methods', 'Who was the participant, and which BrainGate2 implant configuration was used?'),
            PaperQuestion('Methods', 'Which cortical targets were selected and why were they relevant to speech?'),
            PaperQuestion('Methods', 'How did the Copy Task and Conversation Mode differ?'),
            PaperQuestion('Methods', 'How did the decoder turn intracortical activity into phonemes, words, and sentences?'),
            PaperQuestion('Methods', 'How were calibration speed, word error rate, phoneme error rate, confidence intervals, and long-term use evaluated?'),
        ),
    ),
    Mission(
        key='handwriting-brain-to-text',
        title='Handwriting Brain-to-Text',
        source='Mission paper: Willett et al., Nature 2021',
        prompt=(
            'Answer the 10 paper questions. Focus on how attempted handwriting '
            'is decoded from intracortical motor-cortex activity into real-time text.'
        ),
        key_facts=(
            KeyFact('builds an intracortical BCI for brain-to-text communication', ('intracortical', 'bci', 'brain-to-text', 'communication')),
            KeyFact('decodes attempted handwriting movements', ('attempted handwriting', 'handwriting', 'write', 'writing')),
            KeyFact('records from motor cortex hand-knob precentral gyrus arrays', ('motor cortex', 'hand knob', 'precentral gyrus', 'microelectrode arrays')),
            KeyFact('studies BrainGate participant T5 with spinal cord injury', ('braingate', 't5', 'spinal cord injury', 'c4')),
            KeyFact('uses recurrent neural network character decoding', ('recurrent neural network', 'rnn', 'character probabilities', 'decoder')),
            KeyFact('uses a 31-character alphabet including punctuation and space', ('31', 'alphabet', 'punctuation', 'space', 'characters')),
            KeyFact('uses HMM forced alignment and synthetic sentence training', ('hmm', 'hidden markov', 'forced alignment', 'synthetic sentences')),
            KeyFact('achieves 90 characters per minute online', ('90 characters per minute', '90 cpm', 'typing speed', 'online')),
            KeyFact('reports 94.1 percent raw online accuracy', ('94.1', 'raw accuracy', 'online accuracy', 'error rate')),
            KeyFact('exceeds 99 percent offline accuracy with autocorrect language model', ('99', 'autocorrect', 'language model', 'offline accuracy')),
        ),
        reward_item='handwriting_decoder',
        reward_name='Handwriting Decoder',
        badge='BCI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A BCI artifact for attempted-handwriting communication: BrainGate T5, '
            'hand-knob motor-cortex arrays, RNN character decoding, HMM alignment, '
            'language-model autocorrect, and rapid real-time brain-to-text output.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'Why might attempted handwriting support faster BCI communication than point-and-click cursor typing?'),
            PaperQuestion('Conceptual', 'What does this paper show about preserved fine-motor representations years after paralysis?'),
            PaperQuestion('Conceptual', 'Why is a 31-character alphabet enough for open-ended text communication?'),
            PaperQuestion('Conceptual', 'Why does language-model autocorrect matter for usability?'),
            PaperQuestion('Conceptual', 'What are the main limits of this single-participant intracortical demonstration?'),
            PaperQuestion('Methods', 'Where were the arrays implanted and what neural signals were decoded?'),
            PaperQuestion('Methods', 'How did the RNN convert neural activity into character probabilities?'),
            PaperQuestion('Methods', 'How were HMM forced alignment and character templates used to label training data?'),
            PaperQuestion('Methods', 'How did synthetic sentences expand the training set for the decoder?'),
            PaperQuestion('Methods', 'How were online speed, raw accuracy, and offline autocorrect accuracy measured?'),
        ),
    ),
    Mission(
        key='bimanual-typing-neuroprosthesis',
        title='Bimanual Typing Neuroprosthesis',
        source='Mission paper: Jude et al., Nature Neuroscience 2026',
        prompt=(
            'Answer the 10 paper questions. Focus on how attempted finger '
            'movements are decoded into bimanual QWERTY typing for people with paralysis.'
        ),
        key_facts=(
            KeyFact('develops an intracortical BCI typing neuroprosthesis', ('intracortical', 'ibci', 'typing neuroprosthesis', 'brain-computer interface')),
            KeyFact('uses bimanual QWERTY keyboard functionality', ('bimanual', 'qwerty', 'keyboard', 'typing')),
            KeyFact('decodes attempted finger movements', ('attempted finger', 'finger movements', 'fingers', 'finger')),
            KeyFact('studies two iBCI clinical trial participants with tetraplegia', ('two participants', 'two ibci', 'tetraplegia', 'clinical trial')),
            KeyFact('participants include ALS and spinal cord injury cases', ('als', 'amyotrophic lateral sclerosis', 'spinal cord injury', 'sci')),
            KeyFact('records from precentral gyrus motor arrays', ('precentral gyrus', 'motor cortex', 'arrays', 'neuroport')),
            KeyFact('can decode with as few as 30 calibration sentences', ('30 calibration', 'calibration sentences', '30 sentences', 'calibration')),
            KeyFact('uses a 5-gram language model for sentence decoding', ('5-gram', 'language model', 'sentence decoding', 'word model')),
            KeyFact('reaches 110 characters per minute or 22 words per minute', ('110 characters', '110 cpm', '22 words', '22 wpm')),
            KeyFact('reports a 1.6 percent word error rate', ('1.6', 'word error rate', 'wer', 'error rate')),
        ),
        reward_item='typing_neuroprosthesis',
        reward_name='Typing Neuroprosthesis',
        badge='BCI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A BCI artifact for bimanual QWERTY typing: attempted finger movements, '
            'precentral-gyrus arrays, two BrainGate/iBCI participants, rapid calibration, '
            '5-gram language modeling, and high-throughput text output.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'Why is QWERTY typing a useful communication paradigm for an intracortical BCI?'),
            PaperQuestion('Conceptual', 'Why might attempted finger movements be easier or more intuitive than cursor-based letter selection?'),
            PaperQuestion('Conceptual', 'What does successful bimanual typing imply about preserved motor representations after paralysis?'),
            PaperQuestion('Conceptual', 'Why does fast calibration matter for practical daily use?'),
            PaperQuestion('Conceptual', 'What remaining limitations come from testing two participants?'),
            PaperQuestion('Methods', 'Which participants were studied and what conditions caused their tetraplegia?'),
            PaperQuestion('Methods', 'Where were neural signals recorded, and what array coverage was used?'),
            PaperQuestion('Methods', 'How are attempted finger movements mapped onto QWERTY key selection?'),
            PaperQuestion('Methods', 'How did 30 calibration sentences and the 5-gram language model affect decoding?'),
            PaperQuestion('Methods', 'How were speed, words per minute, and word error rate evaluated?'),
        ),
    ),
    Mission(
        key='finger-quadcopter-bci',
        title='Finger Quadcopter BCI',
        source='Mission paper: Willsey et al., Nature Medicine 2025',
        prompt=(
            'Answer the 10 paper questions. Focus on how continuous finger '
            'decoding becomes high-DOF computer and game control.'
        ),
        key_facts=(
            KeyFact('develops a high-performance finger-based intracortical BCI', ('finger-based', 'intracortical', 'bci', 'ibci')),
            KeyFact('uses a virtual quadcopter game as a control task', ('quadcopter', 'virtual', 'game', 'obstacle course')),
            KeyFact('studies BrainGate2 participant T5 with C4 spinal cord injury', ('braingate2', 't5', 'c4', 'spinal cord injury')),
            KeyFact('records from two 96-channel microelectrode arrays in the left precentral hand knob', ('two 96-channel', 'microelectrode arrays', 'left precentral', 'hand knob')),
            KeyFact('decodes three independent finger groups with four degrees of freedom', ('three independent', 'finger groups', 'four degrees', '4d')),
            KeyFact('thumb control uses flexion-extension and abduction-adduction axes', ('thumb', 'flexion', 'extension', 'abduction', 'adduction')),
            KeyFact('index-middle and ring-little fingers are decoded as grouped one-dimensional arcs', ('index-middle', 'ring-little', '1d', 'finger groups')),
            KeyFact('uses spike-band power and a temporally convolved feed-forward neural network', ('spike-band power', 'sbp', 'feed-forward neural network', 'temporally convolved')),
            KeyFact('trains with open-loop trials and closed-loop ReFIT updates', ('open-loop', 'closed-loop', 'refit', 'training')),
            KeyFact('evaluates performance with target acquisition rate, completion time, throughput, and dSNR', ('target acquisition', 'completion time', 'throughput', 'dsnr')),
        ),
        reward_item='neural_quadcopter',
        reward_name='Neural Quadcopter',
        badge='BCI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A BCI artifact for dexterous game control: BrainGate2, two '
            'left-hand-knob arrays, spike-band-power decoding, four-DOF '
            'continuous finger control, ReFIT updates, dSNR analysis, and '
            'virtual quadcopter navigation.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'Why is finger decoding useful beyond standard 2D cursor control?'),
            PaperQuestion('Conceptual', 'Why is a video game or quadcopter task a serious BCI endpoint rather than just a demo?'),
            PaperQuestion('Conceptual', 'What does four-degree-of-freedom finger control add compared with simpler grasp or cursor BCIs?'),
            PaperQuestion('Conceptual', 'Why does the paper emphasize recreation, enablement, and social connectedness?'),
            PaperQuestion('Conceptual', 'What are the main limitations of this single-participant intracortical study?'),
            PaperQuestion('Methods', 'Who was the participant, and where were the microelectrode arrays implanted?'),
            PaperQuestion('Methods', 'How were thumb, index-middle, and ring-little movements represented as decoder outputs?'),
            PaperQuestion('Methods', 'How did the temporally convolved feed-forward network use spike-band power to decode finger velocities?'),
            PaperQuestion('Methods', 'How were open-loop training, closed-loop training, and ReFIT updates used?'),
            PaperQuestion('Methods', 'How were 2D versus 4D performance, target acquisition, throughput, dSNR, and quadcopter navigation evaluated?'),
        ),
    ),
    Mission(
        key='refit-kf-neural-prosthesis',
        title='ReFIT-KF Neural Prosthesis',
        source='Mission paper: Gilja et al., Nature Neuroscience 2012',
        prompt=(
            'Answer the 10 paper questions. Focus on how closed-loop decoder '
            'training turns neural activity into faster, steadier cursor control.'
        ),
        key_facts=(
            KeyFact('addresses low-performance cursor control as a barrier to clinical translation', ('low performance', 'clinical translation', 'cursor control', 'neural prosthesis')),
            KeyFact('introduces the recalibrated feedback intention-trained Kalman filter', ('refit-kf', 'recalibrated', 'feedback intention-trained', 'kalman filter')),
            KeyFact('uses a closed-loop control perspective rather than only open-loop arm kinematics', ('closed-loop', 'closed loop', 'control perspective', 'online neural control')),
            KeyFact('estimates intended velocity by rotating decoded velocities toward the target', ('intended velocity', 'rotate', 'toward the target', 'target direction')),
            KeyFact('assumes zero velocity during target hold periods', ('zero velocity', 'hold period', 'hold time', 'maintain cursor position')),
            KeyFact('models intended velocity separately from cursor position effects', ('position', 'velocity', 'separately', 'position-based')),
            KeyFact('records from 96-channel Utah arrays in PMd and M1 of two rhesus macaques', ('96-channel', 'utah array', 'pmd', 'm1', 'rhesus')),
            KeyFact('uses threshold-crossing spike counts in 50 ms bins instead of spike sorting', ('threshold crossing', '50 ms', 'spike counts', 'no spike sorting')),
            KeyFact('outperforms Velocity-KF with straighter paths, better stopping, and faster acquisition', ('velocity-kf', 'straighter', 'stopping', 'acquisition time')),
            KeyFact('generalizes to pinball and maze tasks and remains stable across many months', ('pinball', 'maze', 'generalization', '280 sessions', 'years')),
        ),
        reward_item='refit_cursor',
        reward_name='ReFIT Cursor',
        badge='BCI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A BCI artifact for closed-loop cursor control: ReFIT-KF, intended '
            'velocity estimation, position-versus-velocity modeling, threshold '
            'crossings, Fitts law throughput, pinball and maze generalization, '
            'and stable multi-year intracortical array performance.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What performance problem in neural prostheses does ReFIT-KF try to solve?'),
            PaperQuestion('Conceptual', 'Why does closed-loop decoder training differ from fitting a decoder to normal arm movement?'),
            PaperQuestion('Conceptual', 'Why is stopping accurately on a target as important as moving quickly toward it?'),
            PaperQuestion('Conceptual', 'What does generalization to pinball and maze tasks imply about the controller?'),
            PaperQuestion('Conceptual', 'Why does multi-year performance matter for clinical translation?'),
            PaperQuestion('Methods', 'Which animals, implant sites, and electrode arrays were used?'),
            PaperQuestion('Methods', 'How were threshold crossings and 50 ms bins converted into decoder inputs?'),
            PaperQuestion('Methods', 'How does the two-stage ReFIT-KF training procedure estimate intended velocity?'),
            PaperQuestion('Methods', 'How does the model separate intended velocity from cursor position effects?'),
            PaperQuestion('Methods', 'How were Velocity-KF, ReFIT-KF, native arm control, Fitts law throughput, pinball, and maze performance compared?'),
        ),
    ),
    Mission(
        key='neurally-controlled-robotic-arm',
        title='Neurally Controlled Robotic Arm',
        source='Mission paper: Hochberg et al., Nature 2012',
        prompt=(
            'Answer the 10 paper questions. Focus on how BrainGate neural '
            'signals controlled a robotic arm for reach, grasp, and drinking.'
        ),
        key_facts=(
            KeyFact('demonstrates BrainGate robotic reach and grasp in two people with tetraplegia', ('braingate', 'reach', 'grasp', 'tetraplegia')),
            KeyFact('uses a neural interface system to translate motor-cortex activity into assistive device control', ('neural interface system', 'nis', 'motor cortex', 'assistive')),
            KeyFact('studies participants S3 and T2 with long-standing brainstem-stroke tetraplegia and anarthria', ('s3', 't2', 'brainstem stroke', 'anarthria')),
            KeyFact('records from 96-channel intracortical microelectrode arrays in MI arm-hand cortex', ('96-channel', '96 channel', 'microelectrode', 'mi', 'arm-hand', 'motor cortex')),
            KeyFact('uses DLR and DEKA robotic arms for three-dimensional reach-and-grasp tasks', ('dlr', 'deka', 'robotic arm', '3d', 'three-dimensional')),
            KeyFact('controls endpoint velocity and grasp state in parallel from the same cortical ensemble', ('endpoint velocity', 'grasp state', 'parallel', 'cortical ensemble')),
            KeyFact('extracts threshold-crossing rates from 30 kHz neural recordings', ('threshold crossing', 'threshold-crossing', '30 khz', '30khz', 'neural signals')),
            KeyFact('updates decoding in 100 ms bins for S3 and 20 ms bins for T2', ('100 ms', '100ms', '20 ms', '20ms', 'bins')),
            KeyFact('uses open-loop and closed-loop Kalman filter calibration blocks', ('open-loop', 'open loop', 'closed-loop', 'closed loop', 'kalman filter', 'calibration')),
            KeyFact('participant S3 used the robotic arm to drink coffee from a bottle five years after implant', ('drink', 'coffee', 'bottle', 'five years', '5 years')),
        ),
        reward_item='robotic_arm',
        reward_name='Robotic Arm',
        badge='BCI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A BCI artifact for embodied assistive control: BrainGate NIS, MI '
            'microelectrode arrays, DLR and DEKA robotic arms, Kalman endpoint '
            'velocity decoding, parallel grasp-state decoding, and functional '
            'reach, grasp, and drinking demonstrations.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What functional gap does robotic reach-and-grasp control address beyond cursor control?'),
            PaperQuestion('Conceptual', 'Why is it important that participants had long-standing tetraplegia and anarthria?'),
            PaperQuestion('Conceptual', 'What does the bottle-drinking demonstration add beyond target-touch metrics?'),
            PaperQuestion('Conceptual', 'Why does controlling grasp state in parallel with endpoint velocity matter?'),
            PaperQuestion('Conceptual', 'What limitations remain compared with natural able-bodied reaching and grasping?'),
            PaperQuestion('Methods', 'Who were S3 and T2, and where were their arrays implanted?'),
            PaperQuestion('Methods', 'How were threshold-crossing rates extracted from the raw neural recordings?'),
            PaperQuestion('Methods', 'How did open-loop and closed-loop calibration train the Kalman filter?'),
            PaperQuestion('Methods', 'How were the DLR and DEKA arms configured for endpoint velocity and hand grasp?'),
            PaperQuestion('Methods', 'How were touch, grasp, target placement, visual scoring, and drinking-task phases evaluated?'),
        ),
    ),
    Mission(
        key='seven-dof-neuroprosthetic-control',
        title='7-DOF Neuroprosthetic Arm',
        source='Mission paper: Collinger et al., The Lancet 2013',
        prompt=(
            'Answer the 10 paper questions. Focus on how intracortical motor-cortex '
            'signals controlled a 7-degree-of-freedom anthropomorphic prosthetic arm.'
        ),
        key_facts=(
            KeyFact('studies high-performance neuroprosthetic control in an individual with chronic tetraplegia', ('high-performance', 'neuroprosthetic', 'tetraplegia', 'chronic')),
            KeyFact('uses two 96-channel intracortical microelectrode arrays in left motor cortex', ('two 96-channel', '96-channel', 'intracortical', 'microelectrode', 'left motor cortex')),
            KeyFact('controls the Johns Hopkins Modular Prosthetic Limb', ('modular prosthetic limb', 'mpl', 'johns hopkins', 'anthropomorphic')),
            KeyFact('targets seven degrees of freedom: 3D translation, 3D orientation, and 1D grasp', ('7d', 'seven degrees', '3d translation', '3d orientation', '1d grasp')),
            KeyFact('conducts thirteen weeks of brain-machine interface training', ('13 weeks', 'thirteen weeks', 'bmi training', 'training')),
            KeyFact('participant moved the arm freely in 3D by the second day of training', ('second day', 'day 2', '3d workspace', 'freely')),
            KeyFact('robust 7D control was routine after training', ('robust 7d', '7 degree-of-freedom', 'routine', 'after 13 weeks')),
            KeyFact('calibrates decoders from observation-based prosthetic-limb movements', ('observation-based', 'calibration', 'automatic', 'decoder')),
            KeyFact('uses firing rates and a linear velocity decoder to command the prosthetic limb', ('firing rate', 'linear', 'velocity decoder', 'neural decoder')),
            KeyFact('evaluates success rate, completion time, path efficiency, and Action Research Arm Test gains', ('success rate', 'completion time', 'path efficiency', 'arat', 'action research arm test')),
        ),
        reward_item='seven_dof_neuroarm',
        reward_name='7D NeuroArm',
        badge='BCI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A BCI artifact for high-dimensional arm control: two 96-channel '
            'left motor-cortex arrays, observation-based decoder calibration, '
            'the Modular Prosthetic Limb, 7D translation-orientation-grasp control, '
            'path-efficiency gains, and clinically meaningful ARAT performance.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What arm and hand functions does this neuroprosthetic system try to restore?'),
            PaperQuestion('Conceptual', 'Why does seven-degree-of-freedom control matter beyond cursor or endpoint-only control?'),
            PaperQuestion('Conceptual', 'What does rapid progression from 3D movement to routine 7D control suggest about motor-cortical command signals?'),
            PaperQuestion('Conceptual', 'Why are clinical measures such as the Action Research Arm Test important in addition to target metrics?'),
            PaperQuestion('Conceptual', 'What translation barriers remain before this kind of system could be used broadly at home?'),
            PaperQuestion('Methods', 'Who was the participant, and where were the two intracortical arrays implanted?'),
            PaperQuestion('Methods', 'How did observation-based calibration use automatic MPL movements to train the decoder?'),
            PaperQuestion('Methods', 'How were neural firing rates converted into velocity commands for the Modular Prosthetic Limb?'),
            PaperQuestion('Methods', 'How were translation, orientation, grasp targets, computer assistance, chance levels, and path efficiency evaluated?'),
            PaperQuestion('Methods', 'How were functional ARAT and object-manipulation tasks scored over training?'),
        ),
    ),
    Mission(
        key='brain-controlled-muscle-stimulation',
        title='Brain-Controlled Muscle Stimulation',
        source='Mission paper: Ajiboye et al., The Lancet 2017',
        prompt=(
            'Answer the 10 paper questions. Focus on how intracortical BCI '
            'signals command FES to move a paralyzed arm and hand.'
        ),
        key_facts=(
            KeyFact('combines functional electrical stimulation with an intracortical BCI', ('fes', 'functional electrical stimulation', 'ibci', 'intracortical')),
            KeyFact('restores coordinated reaching and grasping using the participant\'s own paralyzed arm', ('own arm', 'paralyzed arm', 'reaching', 'grasping')),
            KeyFact('studies BrainGate2 participant T8 with C4 ASIA A spinal cord injury', ('braingate2', 't8', 'c4', 'asia a', 'spinal cord injury')),
            KeyFact('uses two 96-channel microelectrode arrays in hand-area motor cortex', ('two 96-channel', '96-channel', 'microelectrode arrays', 'hand area', 'motor cortex')),
            KeyFact('implants 36 percutaneous electrodes for hand, elbow, shoulder, and wrist muscle stimulation', ('36', 'percutaneous', 'electrodes', 'hand', 'elbow', 'shoulder', 'wrist')),
            KeyFact('uses a Mobile Arm Support for gravity assistance and humeral abduction/adduction', ('mobile arm support', 'mas', 'gravity', 'humeral', 'abduction', 'adduction')),
            KeyFact('decodes threshold crossings and high-frequency power in 20 ms windows', ('threshold crossing', 'high frequency power', '250', '3000', '20 ms', '20ms')),
            KeyFact('maps neural features through a linear Kalman-like decoder to movement or stimulation commands', ('linear', 'kalman', 'decoder', 'stimulation commands', 'movement commands')),
            KeyFact('compares virtual 3D arm control with FES-actuated arm control', ('virtual', '3d arm', 'fes arm', 'vr', 'comparison')),
            KeyFact('achieves 80-100 percent target accuracy and 11 of 12 coffee-drinking attempts', ('80', '100', 'target', '11 of 12', 'coffee', 'drink')),
        ),
        reward_item='fes_ibci_sleeve',
        reward_name='FES+iBCI Sleeve',
        badge='BCI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A BCI artifact for closed-loop body reanimation: BrainGate2, '
            'motor-cortex arrays, FES electrodes, mobile arm support, '
            '20 ms neural decoding, stimulation pulse-width control, and '
            'functional reaching, drinking, and self-feeding tasks.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What functional gap does FES+iBCI address beyond robotic-arm or cursor control?'),
            PaperQuestion('Conceptual', 'Why is using the participant\'s own arm and hand important for neuroprosthetic translation?'),
            PaperQuestion('Conceptual', 'Why are high-cervical SCI command options like sip-and-puff or head movement insufficient for multi-joint reaching?'),
            PaperQuestion('Conceptual', 'What do the coffee-drinking and self-feeding demonstrations show that target-acquisition trials alone do not?'),
            PaperQuestion('Conceptual', 'What limitations remain before this could become a full-time clinically practical system?'),
            PaperQuestion('Methods', 'Who was participant T8, and what cortical and FES implants did he receive?'),
            PaperQuestion('Methods', 'How were threshold crossings and high-frequency power extracted and used by the decoder?'),
            PaperQuestion('Methods', 'How did the virtual-arm, FES-arm, attempted-movement, and recalibration blocks relate to each other?'),
            PaperQuestion('Methods', 'How did stimulation patterns, pulse width, Mobile Arm Support, and goniometers produce and measure movement?'),
            PaperQuestion('Methods', 'How were success rates, movement times, failure modes, coffee drinking, and self-feeding evaluated?'),
        ),
    ),
    Mission(
        key='brain2qwerty',
        title='Brain2Qwerty',
        source='Mission paper: Levy et al., Nature Neuroscience 2026',
        prompt=(
            'Answer the 10 paper questions. Focus on how Brain2Qwerty decodes '
            'typed sentences from noninvasive brain recordings.'
        ),
        key_facts=(
            KeyFact('introduces noninvasive decoding of typed sentences', ('noninvasive', 'typed sentences', 'brain activity', 'sentence')),
            KeyFact('uses the Brain2Qwerty deep learning architecture', ('brain2qwerty', 'deep learning', 'architecture')),
            KeyFact('decodes MEG and EEG recordings during QWERTY typing', ('meg', 'eeg', 'qwerty', 'typing', 'keyboard')),
            KeyFact('studies a cohort of 35 healthy volunteers', ('35', 'healthy volunteers', 'cohort', 'participants')),
            KeyFact('MEG substantially outperforms EEG', ('meg', 'outperforms', 'eeg', '65')),
            KeyFact('reports about 29 percent character error rate with MEG', ('29', 'character error rate', 'cer', 'meg')),
            KeyFact('best participants reach about 18 percent character error rate', ('18', 'best', 'character error rate', 'cer')),
            KeyFact('uses keystroke-centered time windows as model inputs', ('0.5', 'time window', 'keystroke', '-0.2', '+0.3')),
            KeyFact('combines convolutional, transformer, and language-model modules', ('convolutional', 'transformer', 'language model', 'module')),
            KeyFact('learned representations reflect keyboard layout and typing errors', ('keyboard layout', 'typing errors', 'left-hand', 'right-hand', 'confusion')),
        ),
        reward_item='qwerty_decoder',
        reward_name='QWERTY Decoder',
        badge='BCI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A BCI artifact for noninvasive sentence decoding: Brain2Qwerty, '
            'MEG versus EEG, QWERTY keystroke signals, character error rates, '
            'transformer context, language-model correction, and keyboard-layout representations.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What communication gap does Brain2Qwerty try to address?'),
            PaperQuestion('Conceptual', 'Why is noninvasive decoding important compared with implanted BCIs?'),
            PaperQuestion('Conceptual', 'Why does decoding typed sentences differ from decoding perceived or imagined speech?'),
            PaperQuestion('Conceptual', 'What does the MEG-versus-EEG gap imply for practical noninvasive BCIs?'),
            PaperQuestion('Conceptual', 'Why is character error rate a useful but incomplete success metric here?'),
            PaperQuestion('Methods', 'What task did participants perform while brain activity was recorded?'),
            PaperQuestion('Methods', 'What time window around each keystroke is used as model input?'),
            PaperQuestion('Methods', 'What roles do the convolutional, transformer, and language-model modules play?'),
            PaperQuestion('Methods', 'Which baselines or ablations are used to test Brain2Qwerty?'),
            PaperQuestion('Methods', 'How do keyboard-layout analyses and typing-error analyses support the interpretation of the decoded signal?'),
        ),
    ),
    Mission(
        key='silent-speech-speller',
        title='Silent Speech Speller',
        source='Mission paper: Metzger et al., Nature Communications 2022',
        prompt=(
            'Answer the 10 paper questions. Focus on how silently attempted '
            'speech is turned into letter-by-letter spelling for a person with '
            'severe limb and vocal paralysis.'
        ),
        key_facts=(
            KeyFact('restores communication for severe limb and vocal-tract paralysis', ('communication', 'paralysis', 'vocal-tract', 'anarthria', 'locked-in')),
            KeyFact('uses silent speech attempts without vocal output', ('silent speech', 'silently', 'attempted speech', 'no vocal output')),
            KeyFact('maps 26 NATO code words onto English letters', ('nato', 'code words', '26', 'alpha', 'letters')),
            KeyFact('records from a 128-channel ECoG array over sensorimotor cortex', ('128-channel', 'ecog', 'electrocorticography', 'sensorimotor cortex')),
            KeyFact('combines high-gamma activity and low-frequency signals', ('high-gamma', 'hga', 'low-frequency', 'lfs', 'features')),
            KeyFact('uses 2.5-second letter-decoding windows', ('2.5', '2.5-s', 'time window', 'letter-decoding', 'go cue')),
            KeyFact('uses an RNN classifier for code words and hand-motor command probabilities', ('rnn', 'classifier', 'code-word', 'hand-motor', 'squeeze')),
            KeyFact('uses beam search with a 1152-word vocabulary and language models', ('beam search', '1152', 'vocabulary', 'language model', 'distilgpt-2')),
            KeyFact('achieves 6.13 percent median character error rate and about 29.4 characters per minute', ('6.13', 'character error', 'cer', '29.4', 'characters per minute')),
            KeyFact('generalizes offline to vocabularies over 9000 words but remains a single-participant pilot', ('9000', '9170', 'large vocabulary', 'single participant', 'pilot')),
        ),
        reward_item='silent_speller',
        reward_name='Silent Speller',
        badge='BCI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A BCI artifact for silent-speech spelling: 128-channel ECoG, NATO '
            'code words, high-gamma and low-frequency features, RNN classification, '
            'beam search, language-model rescoring, and large-vocabulary assistive text.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What communication problem does the silent speech speller address?'),
            PaperQuestion('Conceptual', 'Why does letter-by-letter spelling complement direct word decoding?'),
            PaperQuestion('Conceptual', 'Why use NATO code words instead of silently attempting isolated letters?'),
            PaperQuestion('Conceptual', 'How do vocabulary constraints and language models help, and what risks do they introduce?'),
            PaperQuestion('Conceptual', 'What are the main clinical or usability limits of this pilot system?'),
            PaperQuestion('Methods', 'Where was the ECoG array implanted, and what neural signals were recorded?'),
            PaperQuestion('Methods', 'What roles do high-gamma activity and low-frequency signals play in decoding?'),
            PaperQuestion('Methods', 'How do the 2.5-second spelling cycles and RNN classifier produce letter probabilities?'),
            PaperQuestion('Methods', 'How do beam search, the n-gram model, and DistilGPT-2 finalize the sentence?'),
            PaperQuestion('Methods', 'How were error rate, spelling speed, conversational use, and larger-vocabulary generalization evaluated?'),
        ),
    ),
    Mission(
        key='speech-avatar-neuroprosthesis',
        title='Speech Avatar Neuroprosthesis',
        source='Mission paper: Metzger et al., Nature 2023',
        prompt=(
            'Answer the 10 paper questions. Focus on how high-density ECoG '
            'turns silently attempted speech into text, audio speech, and avatar movement.'
        ),
        key_facts=(
            KeyFact('develops a multimodal speech neuroprosthesis for severe paralysis and anarthria', ('multimodal', 'speech neuroprosthesis', 'paralysis', 'anarthria')),
            KeyFact('studies a clinical-trial participant with brainstem stroke and severe vocal paralysis', ('brainstem stroke', 'clinical trial', 'vocal paralysis', 'participant')),
            KeyFact('uses a 253-channel high-density ECoG array over speech sensorimotor cortex', ('253', 'high-density ecog', 'sensorimotor cortex', 'speech cortex')),
            KeyFact('extracts high-gamma activity and low-frequency signals from ECoG', ('high-gamma', 'hga', 'low-frequency', 'ecog features')),
            KeyFact('decodes silently attempted speech rather than overt speech or imagined speech', ('silent', 'attempted speech', 'silently attempted', 'articulators')),
            KeyFact('uses bidirectional RNNs and CTC loss to learn unaligned speech mappings', ('bidirectional rnn', 'ctc', 'connectionist temporal classification', 'unaligned')),
            KeyFact('text decoding predicts phones and uses CTC beam search plus a language model', ('phone', 'beam search', 'language model', 'text decoding')),
            KeyFact('reports large-vocabulary text output around 78 words per minute and 25 percent WER', ('78 words per minute', '78 wpm', '25', 'word error rate', 'wer')),
            KeyFact('speech synthesis uses HuBERT speech units, mel spectrograms, vocoding, and personalized voice conversion', ('hubert', 'mel spectrogram', 'vocoder', 'voice conversion', 'personalized voice')),
            KeyFact('avatar decoding maps neural activity to articulatory gestures and non-speech orofacial movements', ('avatar', 'articulatory gestures', 'orofacial', 'facial animation')),
        ),
        reward_item='speech_avatar_rig',
        reward_name='Speech Avatar Rig',
        badge='BCI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A BCI artifact for embodied speech restoration: 253-channel ECoG, '
            'silently attempted speech, phone decoding, CTC beam search, HuBERT '
            'speech units, personalized voice synthesis, and facial-avatar control.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What communication problem does the speech avatar neuroprosthesis address beyond ordinary text output?'),
            PaperQuestion('Conceptual', 'Why are audio voice and facial-avatar motion important for embodied communication?'),
            PaperQuestion('Conceptual', 'Why does silently attempted speech differ from imagined or inner speech?'),
            PaperQuestion('Conceptual', 'What does preserved articulatory structure imply after many years of paralysis?'),
            PaperQuestion('Conceptual', 'What are the main clinical and engineering limitations of this single-participant demonstration?'),
            PaperQuestion('Methods', 'Where was the ECoG array implanted, and how many recording channels were used?'),
            PaperQuestion('Methods', 'Which neural features were extracted from the ECoG signals?'),
            PaperQuestion('Methods', 'How do bidirectional RNNs, CTC loss, beam search, and the language model produce text?'),
            PaperQuestion('Methods', 'How do HuBERT units, mel spectrograms, vocoding, and voice conversion produce speech audio?'),
            PaperQuestion('Methods', 'How were avatar gestures and performance metrics such as WER, WPM, MCD, and DTW correlations evaluated?'),
        ),
    ),
    Mission(
        key='tactile-icms-feedback',
        title='Tactile ICMS Feedback',
        source='Mission paper: Greenspon et al., Nature Biomedical Engineering 2024',
        prompt=(
            'Answer the 10 paper questions. Focus on how multi-electrode ICMS '
            'can make artificial touch more stable, localizable, and useful for bionic hands.'
        ),
        key_facts=(
            KeyFact('restores tactile feedback for brain-controlled bionic hands using ICMS', ('tactile feedback', 'bionic hand', 'icms', 'intracortical microstimulation')),
            KeyFact('stimulates primary somatosensory cortex in Brodmann area 1', ('somatosensory cortex', 's1', 'brodmann', 'area 1')),
            KeyFact('studies three participants with chronic cervical spinal cord injury', ('three participants', 'cervical', 'spinal cord injury', 'sci')),
            KeyFact('each main participant had four microelectrode arrays including S1 and motor cortex arrays', ('four arrays', 'microelectrode arrays', 'motor cortex', 's1 arrays')),
            KeyFact('projected fields are focal hotspots with diffuse borders', ('projected field', 'pf', 'focal hotspot', 'diffuse borders')),
            KeyFact('projected-field locations remain stable across two to seven years', ('stable', '2-7 years', 'seven years', 'years')),
            KeyFact('projected fields mostly lie within matching natural receptive fields', ('receptive field', 'rf', 'within', 'somatotopic')),
            KeyFact('amplitude and frequency change percept size and intensity', ('amplitude', 'frequency', 'intensity', 'percept size')),
            KeyFact('quartets of electrodes with overlapping projected fields improve localization and force range', ('quartets', 'overlapping', 'multi-electrode', 'localization', 'dynamic range')),
            KeyFact('biomimetic multi-electrode feedback improves bionic-hand compliance discrimination', ('biomimetic', 'compliance discrimination', 'lstm', '7.5', '25')),
        ),
        reward_item='tactile_feedback_glove',
        reward_name='Tactile Feedback Glove',
        badge='BCI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A BCI artifact for artificial touch: S1 microelectrode arrays, '
            'stable projected fields, receptive-field mapping, sensor-to-electrode '
            'force feedback, biomimetic ICMS, and bionic-hand compliance discrimination.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'Why is tactile feedback important for useful brain-controlled bionic hands?'),
            PaperQuestion('Conceptual', 'Why does projected-field stability matter for long-term BCI calibration?'),
            PaperQuestion('Conceptual', 'What does the relation between projected fields and receptive fields imply about preserved somatotopy after spinal cord injury?'),
            PaperQuestion('Conceptual', 'Why might multi-electrode stimulation be more useful than single-electrode stimulation for touch feedback?'),
            PaperQuestion('Conceptual', 'What are the main safety, usability, and generalization limits of this study?'),
            PaperQuestion('Methods', 'Which participants were studied, and where were the sensory and motor arrays implanted?'),
            PaperQuestion('Methods', 'How were projected fields mapped, thresholded, and tested for stability over years?'),
            PaperQuestion('Methods', 'How were ICMS amplitude, frequency, JNDs, and discriminable force levels quantified?'),
            PaperQuestion('Methods', 'How were bionic-hand sensors mapped to somatotopic single-electrode or multi-electrode stimulation?'),
            PaperQuestion('Methods', 'How did the LSTM aperture decoder and biomimetic force-encoding algorithm support the compliance discrimination task?'),
        ),
    ),
    Mission(
        key='tactile-object-icms',
        title='Tactile Object ICMS',
        source='Mission paper: Verbaarschot et al., Nature Communications 2025',
        prompt=(
            'Answer the 10 paper questions. Focus on how customized ICMS '
            'turns stimulation parameters into object-specific artificial touch.'
        ),
        key_facts=(
            KeyFact('restores richer tactile object qualities using customized ICMS', ('object-specific', 'tactile characteristics', 'icms', 'artificial touch')),
            KeyFact('studies three individuals with tetraplegia or spinal cord injury', ('three', 'tetraplegia', 'spinal cord injury', 'sci')),
            KeyFact('stimulates Brodmann area 1 in primary somatosensory cortex', ('brodmann', 'area 1', 's1', 'somatosensory cortex')),
            KeyFact('uses three selected electrodes that evoke right-hand percepts', ('three electrodes', 'right hand', 'palmar', 'electrodes')),
            KeyFact('maps artificial touch for cat, apple, towel, toast, and key objects', ('cat', 'apple', 'towel', 'toast', 'key')),
            KeyFact('lets participants tune amplitude, frequency, biomimetic factor, and drag', ('amplitude', 'frequency', 'biomimetic', 'drag')),
            KeyFact('blinds and randomizes the stimulation parameter mapping during exploration', ('blinded', 'random', 'parameter', 'axes')),
            KeyFact('uses replay trials without visual object cues to test discriminability', ('replay', 'without visual', 'no visual', 'gray rectangle')),
            KeyFact('uses LDA classifiers and permutation tests to decode objects and features', ('lda', 'linear discriminant', 'permutation', 'classifier')),
            KeyFact('finds compliance and temperature help explain the artificial percepts', ('compliance', 'temperature', 'features', 'tactile similarity')),
        ),
        reward_item='object_touch_palette',
        reward_name='Object Touch Palette',
        badge='BCI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A BCI artifact for object-specific artificial touch: customized '
            'S1 ICMS, blinded participant-guided parameter search, replay '
            'discrimination, tactile feature labels, and LDA analyses of '
            'compliance and temperature.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'Why is restoring object-specific tactile quality harder than restoring touch location or intensity?'),
            PaperQuestion('Conceptual', 'Why let participants tune their own ICMS parameters instead of testing one fixed parameter grid?'),
            PaperQuestion('Conceptual', 'What does above-chance replay without visual cues show about artificial touch?'),
            PaperQuestion('Conceptual', 'How can visual context both help and bias interpretation of ICMS sensations?'),
            PaperQuestion('Conceptual', 'What are the main clinical or engineering limitations of this study?'),
            PaperQuestion('Methods', 'Which participants, implants, and electrodes were used?'),
            PaperQuestion('Methods', 'How did the tablet object-sensation mapping task work?'),
            PaperQuestion('Methods', 'How were amplitude, frequency, biomimetic factor, and drag parameterized and randomized?'),
            PaperQuestion('Methods', 'How did replay and delayed replay sessions test discriminability and stability?'),
            PaperQuestion('Methods', 'How were LDA classifiers, permutation tests, Euclidean distances, and tactile-feature labels used?'),
        ),
    ),
    Mission(
        key='human-level-control-deep-rl',
        title='Human-Level Deep RL',
        source='Mission paper: Mnih et al., Nature 2015',
        prompt=(
            'Answer the 10 paper questions. Focus on how DQN learns useful '
            'control policies directly from pixels and rewards.'
        ),
        key_facts=(
            KeyFact('introduces a deep Q-network that combines deep learning and reinforcement learning', ('deep q-network', 'dqn', 'deep learning', 'reinforcement learning')),
            KeyFact('learns policies directly from high-dimensional sensory input', ('high-dimensional', 'sensory input', 'pixels', 'raw input')),
            KeyFact('uses game score as the reward signal', ('game score', 'reward', 'score', 'reinforcement')),
            KeyFact('tests one algorithm on 49 Atari 2600 games', ('49', 'atari', '2600', 'games')),
            KeyFact('uses the same network architecture, learning algorithm, and hyperparameters across games', ('same architecture', 'same algorithm', 'hyperparameters', 'across games')),
            KeyFact('uses a convolutional neural network to approximate action values', ('convolutional', 'q-value', 'action-value', 'q network')),
            KeyFact('uses Q-learning and Bellman targets to update action values', ('q-learning', 'bellman', 'target value', 'action-value')),
            KeyFact('uses experience replay to randomize samples and improve stability', ('experience replay', 'replay memory', 'random minibatch', 'correlations')),
            KeyFact('uses a separate target Q-network to reduce instability', ('target q-network', 'separate target', 'periodically updated', 'stability')),
            KeyFact('beats previous algorithms on most games but struggles with temporally extended planning', ('previous algorithms', 'professional human', 'montezuma', 'extended planning')),
        ),
        reward_item='deep_q_core',
        reward_name='Deep Q Core',
        badge='NeuroAI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A NeuroAI artifact for end-to-end control: convolutional value '
            'functions, Q-learning, experience replay, target networks, Atari '
            'benchmarks, and the limits of reactive policies on planning-heavy '
            'tasks.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What problem does DQN solve compared with earlier reinforcement-learning systems that required hand-crafted features?'),
            PaperQuestion('Conceptual', 'Why is learning directly from pixels and reward important for general agents?'),
            PaperQuestion('Conceptual', 'How does combining deep learning with Q-learning connect perception to action?'),
            PaperQuestion('Conceptual', 'Why is Atari a useful but limited benchmark for intelligence or NeuroAI?'),
            PaperQuestion('Conceptual', 'What do DQN failures on planning-heavy games imply about the limits of the approach?'),
            PaperQuestion('Methods', 'What inputs, outputs, and reward signal does the DQN agent receive from each Atari game?'),
            PaperQuestion('Methods', 'What convolutional network architecture is used to estimate action values?'),
            PaperQuestion('Methods', 'How does the Q-learning Bellman target define the learning objective?'),
            PaperQuestion('Methods', 'How do experience replay, random minibatches, and the replay memory stabilize training?'),
            PaperQuestion('Methods', 'How are the target Q-network, reward/error clipping, fixed hyperparameters, and professional-human comparison used in the evaluation?'),
        ),
    ),
    Mission(
        key='alphago-policy-value-search',
        title='AlphaGo Policy-Value Search',
        source='Mission paper: Silver et al., Nature 2016',
        prompt=(
            'Answer the 10 paper questions. Focus on how AlphaGo combines '
            'deep policy/value networks with Monte Carlo tree search.'
        ),
        key_facts=(
            KeyFact('frames Go as difficult because of huge search breadth and depth', ('go', 'search space', 'breadth', 'depth', 'infeasible')),
            KeyFact('uses policy networks to select or prioritize moves', ('policy network', 'select moves', 'move probabilities', 'actions')),
            KeyFact('uses value networks to evaluate board positions', ('value network', 'evaluate positions', 'predicts outcome', 'board positions')),
            KeyFact('represents the board as a 19x19 image processed by convolutional layers', ('19x19', 'convolutional', 'board position', 'image')),
            KeyFact('trains a supervised policy network from human expert games', ('supervised learning', 'human expert', 'kgs', 'expert moves')),
            KeyFact('uses 30 million KGS positions and reaches 57.0 percent expert-move prediction accuracy', ('30 million', '57.0', 'expert-move', 'prediction accuracy')),
            KeyFact('improves the policy with reinforcement learning from self-play', ('reinforcement learning', 'self-play', 'policy gradient', 'winning games')),
            KeyFact('trains the value network to predict winners from self-play positions', ('value network', 'self-play', 'predict winner', 'outcome')),
            KeyFact('combines policy/value networks with Monte Carlo tree search', ('monte carlo tree search', 'mcts', 'rollouts', 'tree search')),
            KeyFact('achieves a 99.8 percent win rate against other Go programs and beats Fan Hui 5 to 0', ('99.8', 'fan hui', '5-0', 'european champion', 'professional player')),
        ),
        reward_item='policy_value_stone',
        reward_name='Policy-Value Stone',
        badge='NeuroAI',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A NeuroAI artifact for hybrid search and learning: supervised '
            'policy networks, self-play reinforcement learning, value networks, '
            'fast rollouts, and Monte Carlo tree search for strategic planning.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'Why was full-sized Go considered hard for AI before AlphaGo?'),
            PaperQuestion('Conceptual', 'How do policy networks and value networks reduce the effective search problem?'),
            PaperQuestion('Conceptual', 'Why combine supervised learning from expert games with reinforcement learning from self-play?'),
            PaperQuestion('Conceptual', 'What does AlphaGo show about hybrid systems that combine neural networks with search?'),
            PaperQuestion('Conceptual', 'What are the limits of using board games like Go as evidence for general intelligence?'),
            PaperQuestion('Methods', 'How is the Go board represented as input to the policy and value networks?'),
            PaperQuestion('Methods', 'How was the supervised policy network trained and evaluated on expert moves?'),
            PaperQuestion('Methods', 'How did self-play reinforcement learning improve the policy network?'),
            PaperQuestion('Methods', 'How was the value network trained to predict game outcomes?'),
            PaperQuestion('Methods', 'How does Monte Carlo tree search combine prior probabilities, value estimates, and rollouts during move selection?'),
        ),
    ),
    Mission(
        key='cognitive-maps-programs',
        title='Cognitive Maps as Programs',
        source='Mission paper: Kryven, Wyeth, Curtis, Ellis, arXiv 2025',
        prompt=(
            'Answer the 10 paper questions. Focus on how programmatic cognitive '
            'maps compress structured worlds and explain resource-efficient '
            'human planning.'
        ),
        key_facts=(
            KeyFact('cognitive maps can be represented as generative programs', ('cognitive map', 'generative program', 'programmatic', 'programs')),
            KeyFact('programs exploit predictable structure and redundancy', ('predictable', 'structured', 'redundancy', 'symmetry', 'repeated')),
            KeyFact('contrasts programmatic maps with direct spatial layout encoding', ('directly encoding', 'spatial layout', 'full layout', 'not direct')),
            KeyFact('studies resource-efficient human planning', ('resource-efficient', 'cognitive resources', 'planning', 'efficient')),
            KeyFact('uses a partially observable Maze Search Task', ('maze search task', 'mst', 'partially observable', 'grid-world', 'hidden')),
            KeyFact('people show modular planning strategies', ('modular planning', 'modular', 'fragments', 'module')),
            KeyFact('models maps as fragments plus a reconstruction program', ('fragments', 'reconstruct', 'programmatic representation', 'generative map module')),
            KeyFact('fragment-based planning reuses policies across repeated fragments', ('reuse', 'policy', 'fragment-based', 'decision tree', 'computed once')),
            KeyFact('uses an LLM to synthesize programmatic map representations', ('llm', 'gpt4', 'program synthesis', 'human priors', 'language model')),
            KeyFact('outperforms optimal and limited-horizon planning baselines at predicting behavior', ('expected utility', 'discounted utility', 'limited horizon', 'baseline', 'predicts people')),
        ),
        reward_item='program_map',
        reward_name='Program Map',
        badge='Cognitive Science',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A map artifact for cognitive science and NeuroAI: program-like '
            'cognitive maps, modular planning, POMDP approximations, LLM priors, '
            'and fragment reuse in structured worlds.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'Why represent cognitive maps as generative programs instead of full layouts?'),
            PaperQuestion('Conceptual', 'How does predictable world structure make planning easier?'),
            PaperQuestion('Conceptual', 'Why can modular planning be locally optimal but globally suboptimal?'),
            PaperQuestion('Conceptual', 'What role do human prior expectations play in the model?'),
            PaperQuestion('Conceptual', 'What behavioral evidence supports programmatic cognitive maps?'),
            PaperQuestion('Methods', 'How does the Maze Search Task create partial observability?'),
            PaperQuestion('Methods', 'How is the planning problem formulated as a POMDP?'),
            PaperQuestion('Methods', 'How does the Generative Map Module synthesize fragments and programs?'),
            PaperQuestion('Methods', 'How does Fragment-based Planning reuse computation across repeated fragments?'),
            PaperQuestion('Methods', 'Which baselines and metrics are used to compare the model to humans?'),
        ),
    ),
    Mission(
        key='clone-structured-cognitive-graphs',
        title='Clone-Structured Cognitive Graphs',
        source='Mission paper: George et al., Nature Communications 2021',
        prompt=(
            'Answer the 10 paper questions. Focus on how clone-structured '
            'cognitive graphs learn cognitive maps from aliased observation '
            'sequences and support flexible planning.'
        ),
        key_facts=(
            KeyFact('cognitive maps represent spatial and conceptual relationships for flexible behavior', ('cognitive map', 'spatial', 'conceptual', 'flexible behavior', 'planning')),
            KeyFact('the problem is aliased observations that require context-specific interpretation', ('aliased', 'aliasing', 'ambiguous observation', 'context', 'same observation')),
            KeyFact('introduces clone-structured cognitive graphs', ('clone-structured cognitive graph', 'cscg', 'clone structured', 'cognitive graph')),
            KeyFact('clones map one observation to multiple hidden contextual states', ('clone', 'clones', 'hidden state', 'different contexts', 'same observation')),
            KeyFact('uses an action-augmented cloned hidden Markov model', ('hidden markov', 'hmm', 'action-augmented', 'probabilistic sequence', 'markov')),
            KeyFact('learns clone allocation and transition structure with expectation maximization', ('expectation maximization', 'em', 'transition matrix', 'pseudocount', 'learning')),
            KeyFact('uses belief propagation and smoothing for exact inference under uncertainty', ('belief propagation', 'bp', 'smoothing', 'soft evidence', 'uncertainty')),
            KeyFact('discovers spatial relations from aliased sensory streams', ('spatial relations', 'aliased sensations', 'sensory stream', 'room', 'maze')),
            KeyFact('explains hippocampal splitter cells, lap-specific responses, and place-cell remapping', ('splitter cells', 'lap-specific', 'place cell remapping', 'hippocampal', 'event-specific')),
            KeyFact('reveals latent modularity for hierarchical abstraction and planning', ('latent modularity', 'hierarchical planning', 'community detection', 'vicarious', 'abstraction')),
        ),
        reward_item='clone_graph',
        reward_name='Clone Graph',
        badge='Cognitive Science',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A cognitive-map artifact for CSCGs: cloned hidden states, aliased '
            'observations, action-conditioned transitions, EM learning, belief '
            'propagation, hippocampal remapping, and hierarchical planning.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What problem do aliased observations create for cognitive maps?'),
            PaperQuestion('Conceptual', 'Why do cloned states help an agent split or merge contexts?'),
            PaperQuestion('Conceptual', 'How can a learned CSCG support flexible planning or vicarious evaluation?'),
            PaperQuestion('Conceptual', 'How does the paper connect spatial maps with conceptual or relational maps?'),
            PaperQuestion('Conceptual', 'Which hippocampal phenomena is the model trying to unify?'),
            PaperQuestion('Methods', 'How is a CSCG related to a cloned hidden Markov model?'),
            PaperQuestion('Methods', 'How does expectation maximization allocate clones and learn transitions?'),
            PaperQuestion('Methods', 'How does belief propagation handle uncertainty or noisy observations?'),
            PaperQuestion('Methods', 'Which experiments test learning from aliased sequences, transitive inference, and transfer?'),
            PaperQuestion('Methods', 'How is latent modularity used for hierarchical planning, and how is it evaluated?'),
        ),
    ),
    Mission(
        key='centaur-cognition',
        title='Centaur Cognition Model',
        source='Mission paper: Binz et al., arXiv 2024',
        prompt=(
            'Answer the 10 paper questions. Focus on how Centaur uses '
            'large-scale psychology data and language-model finetuning to '
            'predict human behavior across tasks.'
        ),
        key_facts=(
            KeyFact('introduces Centaur as a foundation model of human cognition', ('centaur', 'foundation model', 'human cognition')),
            KeyFact('fine-tunes a large language model to predict human behavior', ('fine-tune', 'finetune', 'language model', 'llama', 'behavior')),
            KeyFact('trains on Psych-101 psychology experiments', ('psych-101', 'psychology', 'experiments', 'dataset')),
            KeyFact('uses trial-by-trial human choices from many participants', ('trial-by-trial', 'choices', 'participants', 'responses')),
            KeyFact('covers many cognitive domains and 160 experiments', ('160', 'multi-armed bandit', 'decision-making', 'memory', 'markov')),
            KeyFact('uses QLoRA low-rank adapters on Llama 3.1 70B', ('qlora', 'low-rank', 'adapter', 'llama 3.1', '70b')),
            KeyFact('masks training loss to focus on human responses', ('masked', 'loss', 'human responses', 'cross-entropy')),
            KeyFact('generalizes to held-out participants and out-of-domain tasks', ('held-out', 'out-of-domain', 'cover story', 'structural', 'novel domain')),
            KeyFact('compares against domain-specific cognitive models and baselines', ('cognitive model', 'baseline', 'negative log-likelihood', 'goodness-of-fit')),
            KeyFact('internal representations become more aligned with neural activity', ('internal representation', 'neural activity', 'fmri', 'alignment', 'brain')),
        ),
        reward_item='centaur_token',
        reward_name='Centaur Token',
        badge='Cognitive Science',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A cognitive-science token for Centaur: Psych-101, trial-by-trial '
            'behavior prediction, QLoRA finetuning, out-of-domain generalization, '
            'and neural-representation alignment.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What makes Centaur a foundation model of human cognition?'),
            PaperQuestion('Conceptual', 'Why train on many psychology experiments instead of one task?'),
            PaperQuestion('Conceptual', 'What does trial-by-trial behavioral prediction test?'),
            PaperQuestion('Conceptual', 'Why does out-of-domain generalization matter for cognitive science?'),
            PaperQuestion('Conceptual', 'What are the risks or limits of replacing hand-built cognitive models with a foundation model?'),
            PaperQuestion('Methods', 'What is Psych-101 and how is it used for training and evaluation?'),
            PaperQuestion('Methods', 'How are experimental trials represented as model inputs?'),
            PaperQuestion('Methods', 'How is Centaur fine-tuned from the base language model?'),
            PaperQuestion('Methods', 'Which baselines or held-out evaluations are used to judge performance?'),
            PaperQuestion('Methods', 'How are internal representations analyzed against cognitive or neural structure?'),
        ),
    ),
    Mission(
        key='escape-dimensions',
        title='Escape Dimensions',
        source='Mission paper: Martinelli, Brea, Gerstner, ICML 2026',
        prompt=(
            'Answer the 10 paper questions. Focus on why the lottery-ticket '
            'analogy is misleading and how escape dimensions explain the '
            'optimization benefits of overparameterization.'
        ),
        key_facts=(
            KeyFact('challenges the lottery-ticket analogy for overparameterization', ('lottery ticket', 'lottery-ticket', 'analogy', 'misleading', 'overparameterization')),
            KeyFact('distinguishes the empirical LTH from the lottery-ticket conjecture', ('hypothesis', 'conjecture', 'lth', 'empirical', 'untested')),
            KeyFact('lottery metaphor assumes sufficiency scaling and independence', ('sufficiency', 'scaling', 'independence')),
            KeyFact('subnetworks depend on the rest of the network context', ('context', 'rest of the network', 'embedded', 'not isolated', 'subnetwork')),
            KeyFact('adversarial overparameterization can disrupt a winning ticket', ('adversarial overparameterization', 'advop', 'anti-align', 'disrupt', 'perturb')),
            KeyFact('multi-start optimization is a misleading training picture', ('multi-start', 'parallel search', 'independent trajectories', 'selection')),
            KeyFact('overparameterization adds dimensions for escaping bad minima', ('escape dimensions', 'escape', 'bad local minima', 'sub-optimal minima')),
            KeyFact('bad minima can become saddles when width increases', ('saddle', 'local minima', 'width', 'hidden units', 'fukumizu')),
            KeyFact('bad minima become rarer relative to good minima as width grows', ('rarer', 'rare', 'good minima', 'bad minima', 'width grows')),
            KeyFact('quote survey documents spread of the misleading metaphor', ('semantic scholar', 'quotes', 'sliding window', 'llm', 'manual')),
        ),
        reward_item='escape_compass',
        reward_name='Escape Compass',
        badge='Machine Learning',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A compass artifact for machine-learning theory: lottery-ticket '
            'analogy limits, subnetwork context, loss-landscape geometry, and '
            'escape dimensions in overparameterized networks.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What explanation of overparameterization is the paper criticizing?'),
            PaperQuestion('Conceptual', 'How does the paper distinguish LTH from the lottery-ticket conjecture?'),
            PaperQuestion('Conceptual', 'What do sufficiency, scaling, and independence mean in the analogy?'),
            PaperQuestion('Conceptual', 'Why is multi-start optimization a misleading mental model here?'),
            PaperQuestion('Conceptual', 'What is an escape dimension?'),
            PaperQuestion('Methods', 'How does the paper test whether winning tickets are sufficient when embedded?'),
            PaperQuestion('Methods', 'Compare the LTH, advOP, rndOP, and rnd conditions.'),
            PaperQuestion('Methods', 'How does adversarial overparameterization disrupt a ticket signal?'),
            PaperQuestion('Methods', 'What landscape result supports minima becoming saddles with added width?'),
            PaperQuestion('Methods', 'How were quotes collected and filtered to document metaphor spread?'),
        ),
    ),
    Mission(
        key='nise-drug-binding-proteins',
        title='NISE Drug-Binding Proteins',
        source='Mission paper: Fry, Slaw, Polizzi, Nature 2026',
        prompt=(
            'Answer the 10 paper questions. Focus on how neural iterative '
            'selection-expansion designs de novo drug-binding proteins without '
            'target-specific experimental training data.'
        ),
        key_facts=(
            KeyFact('introduces neural iterative selection-expansion', ('nise', 'neural iterative selection', 'selection-expansion', 'selection expansion')),
            KeyFact('targets zero-shot de novo drug-binding protein design', ('zero-shot', 'de novo', 'drug-binding', 'small-molecule binder')),
            KeyFact('optimizes tripartite self-consistency', ('tripartite self-consistency', 'self-consistency', 'backbone', 'ligand coordinates', 'sequence')),
            KeyFact('iterates sequence design and protein-ligand co-structure prediction', ('iterative', 'sequence design', 'co-structure', 'predict co-structures')),
            KeyFact('uses LASErMPNN for ligand-aware sequence design', ('lasermpnn', 'heterograph', 'ligand-aware', 'sequence', 'side-chain dihedral')),
            KeyFact('uses RFAA or Boltz for protein-ligand co-structure prediction', ('rfaa', 'boltz', 'boltz-2', 'co-structure prediction', 'protein-ligand')),
            KeyFact('ranks designs with confidence and binding metrics', ('ligand plddt', 'p(bind)', 'confidence', 'rmsd', 'ranking')),
            KeyFact('EPIC binds exatecan and protects the lactone ring', ('epic', 'exatecan', 'lactone', 'hydrolysis', 'protects')),
            KeyFact('LASErMPNN proofreading improves EPIC affinity with mutations', ('proofreading', 'q51n', 'm97l', 'mutation', 'improves affinity')),
            KeyFact('APEX binds apixaban tightly and specifically', ('apex', 'apixaban', '80 pm', 'specific', 'off-target')),
        ),
        reward_item='ligand_key',
        reward_name='Ligand Key',
        badge='Protein Design',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A ligand-key artifact for small-molecule binder design: NISE, '
            'LASErMPNN, co-structure prediction, tripartite self-consistency, '
            'EPIC exatecan binding, and APEX apixaban specificity.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What problem in drug-binding protein design does NISE try to solve?'),
            PaperQuestion('Conceptual', 'What does tripartite self-consistency mean in this paper?'),
            PaperQuestion('Conceptual', 'Why is zero-shot design important for small-molecule binders?'),
            PaperQuestion('Conceptual', 'Why does protecting exatecan from hydrolysis matter biologically?'),
            PaperQuestion('Conceptual', 'What makes APEX a strong apixaban-binding result?'),
            PaperQuestion('Methods', 'How do LASErMPNN and RFAA or Boltz interact during a NISE trajectory?'),
            PaperQuestion('Methods', 'What does LASErMPNN learn from protein-ligand co-crystal structures?'),
            PaperQuestion('Methods', 'Which confidence or binding metrics are used to select designs?'),
            PaperQuestion('Methods', 'How did neural proofreading modify EPIC and improve affinity?'),
            PaperQuestion('Methods', 'How were EPIC and APEX experimentally validated?'),
        ),
    ),
    Mission(
        key='ligandforge-discrete-diffusion',
        title='LigandForge Discrete Diffusion',
        source='Mission paper: Watson, bioRxiv 2026',
        prompt=(
            'Answer the 10 paper questions. Focus on how LigandForge uses '
            'pocket-conditioned discrete diffusion to generate peptide binders '
            'without structure prediction at inference.'
        ),
        key_facts=(
            KeyFact('introduces LigandForge for de novo peptide binder design', ('ligandforge', 'peptide binder', 'de novo peptide', 'binder design')),
            KeyFact('uses pocket-conditioned discrete diffusion', ('discrete diffusion', 'pocket-conditioned', 'receptor pocket', 'pocket geometry')),
            KeyFact('generates sequences in a single forward pass', ('single forward pass', 'one forward pass', 'single-pass', 'inference')),
            KeyFact('does not use structure prediction or inverse folding at inference', ('no structure prediction', 'structure-free', 'inverse folding', 'iterative refinement')),
            KeyFact('encodes 48-dimensional receptor pocket features per residue', ('48-dimensional', 'pocket features', 'physicochemical', 'solvent exposure', 'local geometry')),
            KeyFact('uses thermodynamic supervision during training', ('thermodynamic supervision', 'hydrogen bond', 'van der waals', 'salt bridge', 'binding free energy')),
            KeyFact('generated about 490,691 peptides across 150 receptor targets', ('490,691', '150 receptor', '150 targets', 'receptor targets')),
            KeyFact('validated thousands of candidates with Boltz-2', ('boltz-2', '16,475', 'structural validation', 'folded')),
            KeyFact('uses DeltaForge thermodynamic scoring calibrated to PPB-Affinity', ('deltaforge', 'ppb-affinity', 'pearson', '0.83', 'binding free energy')),
            KeyFact('needs experimental binding validation for predicted binders', ('experimental validation', 'spr', 'bli', 'computational hypotheses', 'not validated')),
        ),
        reward_item='ligandforge_peptide',
        reward_name='LigandForge Peptide',
        badge='Protein Design',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A peptide artifact for fast binder generation: LigandForge, '
            'pocket-conditioned discrete diffusion, thermodynamic supervision, '
            'DeltaForge scoring, Boltz-2 validation, and experimental next steps.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What inference bottleneck is LigandForge trying to remove from peptide design?'),
            PaperQuestion('Conceptual', 'What does it mean to compile thermodynamic knowledge into model weights?'),
            PaperQuestion('Conceptual', 'Why does very high sequence throughput change the design strategy?'),
            PaperQuestion('Conceptual', 'How does structure-free sequence generation differ from backbone-sampling design?'),
            PaperQuestion('Conceptual', 'What claims remain computational hypotheses until wet-lab validation?'),
            PaperQuestion('Methods', 'What receptor-pocket features condition the LigandForge model?'),
            PaperQuestion('Methods', 'Which thermodynamic or sequence objectives supervise training?'),
            PaperQuestion('Methods', 'How are generated candidates validated and scored after generation?'),
            PaperQuestion('Methods', 'How is the five-target benchmark against BoltzGen and BindCraft set up?'),
            PaperQuestion('Methods', 'What do the DSSP, GPCR pocket, and multimeric receptor analyses test?'),
        ),
    ),
    Mission(
        key='jam2-pmhc-tcell-engagers',
        title='JAM-2 pMHC T-Cell Engagers',
        source='Mission paper: Nabla Bio, 2026',
        prompt=(
            'Answer the 10 paper questions. Focus on how JAM-2 designs '
            'drug-like pMHC-targeting antibodies and turns them into '
            'bispecific T-cell engagers.'
        ),
        key_facts=(
            KeyFact('uses JAM-2 for de novo pMHC-targeting antibody design', ('jam-2', 'de novo', 'pmhc', 'antibody design')),
            KeyFact('targets intracellular proteins through peptide-MHC class I display', ('intracellular proteome', 'peptide-mhc', 'mhc-i', 'cell surface')),
            KeyFact('pMHC binders must distinguish target peptides from self peptides', ('self-peptide', 'shared mhc', 'single residue', 'selectivity')),
            KeyFact('generated binders for five targets across two HLA alleles', ('five targets', 'two hla', 'hla-a*02:01', 'hla-a*03:01')),
            KeyFact('spans tumor-associated antigens and neoantigens', ('ny-eso-1', 'mage-a4', 'wt1', 'afp', 'kras')),
            KeyFact('uses yeast surface display with pMHC tetramers', ('yeast surface display', 'pmhc tetramer', 'library', 'screened')),
            KeyFact('uses FACS enrichment and next-generation sequencing', ('facs', 'fluorescence-activated', 'ngs', 'sequencing', 'enrichment')),
            KeyFact('reformats binders as VHH anti-CD3 bispecific T-cell engagers', ('vhh', 'anti-cd3', 'bispecific', 't-cell engager', 'tce')),
            KeyFact('reports sub-nanomolar T-cell activation and at least 216-fold selectivity', ('sub-nanomolar', '216-fold', 't-cell activation', 'selectivity')),
            KeyFact('validates KRAS specificity and designed binding with cryo-EM', ('kras g12v', 'g12c', 'wild-type', '0.93', 'cryo-em')),
        ),
        reward_item='pmhc_prism',
        reward_name='pMHC Prism',
        badge='Protein Design',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A prism artifact for pMHC-targeted T-cell engagers: JAM-2, '
            'intracellular proteome access, HLA-specific peptide recognition, '
            'yeast-display screening, T-cell activation, KRAS selectivity, and cryo-EM.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'Why are peptide-MHC targets useful for reaching the intracellular proteome?'),
            PaperQuestion('Conceptual', 'Why is pMHC specificity difficult when many peptides share the same MHC surface?'),
            PaperQuestion('Conceptual', 'What does JAM-2 extend beyond simple binder design in this paper?'),
            PaperQuestion('Conceptual', 'Why does the bispecific T-cell-engager format matter therapeutically?'),
            PaperQuestion('Conceptual', 'What does the KRAS G12V/G12C result show about single-residue discrimination?'),
            PaperQuestion('Methods', 'Which pMHC targets and HLA alleles were used for the design campaign?'),
            PaperQuestion('Methods', 'How did yeast display, pMHC tetramers, FACS, and NGS identify binders?'),
            PaperQuestion('Methods', 'How were selected VHH binders reformatted and tested as T-cell engagers?'),
            PaperQuestion('Methods', 'How were potency, selectivity, and developability measured?'),
            PaperQuestion('Methods', 'What did cryo-EM test about the designed KRAS binding mode?'),
        ),
    ),
    Mission(
        key='protein-hunter',
        title='Protein Hunter',
        source='Mission paper: Cho, Rangel, Bhardwaj, Ovchinnikov, bioRxiv 2025',
        prompt=(
            'Answer the 10 paper questions. Focus on how Protein Hunter turns '
            'structure prediction hallucination into a design loop.'
        ),
        key_facts=(
            KeyFact('starts from all-X or unknown residues', ('all-x', 'x token', 'unknown', 'percent_x')),
            KeyFact('uses diffusion-style structure prediction models', ('diffusion', 'boltz', 'chai', 'alphafold3', 'af3')),
            KeyFact('uses ProteinMPNN or LigandMPNN for redesign', ('proteinmpnn', 'ligandmpnn', 'inverse folding', 'redesign')),
            KeyFact('cycles prediction and redesign', ('cycle', 'iterative', 'repredict', 're-predict', 'self-consistent')),
            KeyFact('optimizes confidence/interface metrics', ('iptm', 'plddt', 'pae', 'confidence', 'high_iptm')),
            KeyFact('applies to diverse binders and targets', ('binder', 'cyclic peptide', 'small molecule', 'dna', 'rna')),
            KeyFact('is fine-tuning-free/lightweight', ('fine-tuning-free', 'fine tuning free', 'lightweight', 'no training')),
            KeyFact('percent_X controls exploration', ('percent_x', 'mixed', 'random amino', 'x residues')),
            KeyFact('supports motif scaffolding or partial redesign', ('motif', 'scaffolding', 'partial redesign', 'multi-motif')),
            KeyFact('still needs experimental validation', ('experimental', 'in silico', 'validate', 'validation', 'not experimentally')),
        ),
        reward_item='protein_hunter_map',
        reward_name='Protein Hunter Map',
        badge='Protein Design',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A design-map artifact for iterative protein discovery: structure '
            'prediction, redesign, confidence filters, and experimental next steps.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What design problem does Protein Hunter target?'),
            PaperQuestion('Conceptual', 'Why begin from an all-X sequence?'),
            PaperQuestion('Conceptual', 'How does hallucination become design?'),
            PaperQuestion('Conceptual', 'Which target classes are supported?'),
            PaperQuestion('Conceptual', 'Why is fine-tuning-free useful?'),
            PaperQuestion('Methods', 'Outline one prediction-redesign cycle.'),
            PaperQuestion('Methods', 'What do Boltz/Chai/AF3 do vs MPNN?'),
            PaperQuestion('Methods', 'What does percent_X control?'),
            PaperQuestion('Methods', 'Which confidence filters matter?'),
            PaperQuestion('Methods', 'What validation gap remains?'),
        ),
    ),
    Mission(
        key='protein-mpnn',
        title='ProteinMPNN',
        source='Mission paper: Dauparas et al., Science 2022',
        prompt=(
            'Answer the 10 paper questions. Focus on inverse folding, backbone '
            'geometry, decoding order, and experimental validation.'
        ),
        key_facts=(
            KeyFact('solves fixed-backbone inverse folding', ('fixed backbone', 'inverse folding', 'backbone', 'sequence design')),
            KeyFact('uses a message-passing graph neural network', ('message passing', 'mpnn', 'graph neural', 'gnn')),
            KeyFact('encodes protein backbone geometry', ('coordinates', 'distance', 'orientation', 'dihedral', 'n ca c o')),
            KeyFact('uses autoregressive/random decoding order', ('autoregressive', 'random decoding', 'decoding order', 'order agnostic')),
            KeyFact('improves sequence recovery over Rosetta', ('52.4', '32.9', 'sequence recovery', 'rosetta')),
            KeyFact('training noise improves robustness', ('noise', 'gaussian', '0.02', '0.3', 'robust')),
            KeyFact('handles interfaces and multichain design', ('interface', 'multi-chain', 'multichain', 'heteromer', 'homomer')),
            KeyFact('ties residues/probabilities for symmetry or constraints', ('tied', 'coupled', 'symmetry', 'probabilities')),
            KeyFact('validated with structural/functional experiments', ('x-ray', 'cryoem', 'functional', 'biolayer', 'experimental')),
            KeyFact('sampling temperature trades diversity and recovery', ('temperature', 'diversity', 'sampling', 'probability')),
        ),
        reward_item='mpnn_gear',
        reward_name='MPNN Gear',
        badge='Protein Design',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A gear artifact for inverse folding: fixed backbones, graph message '
            'passing, decoding order, and sequence-design constraints.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What inverse-folding question is answered?'),
            PaperQuestion('Conceptual', 'Why can backbone geometry guide sequence?'),
            PaperQuestion('Conceptual', 'What does sequence recovery miss?'),
            PaperQuestion('Conceptual', 'Why train with backbone noise?'),
            PaperQuestion('Conceptual', 'Why tie residues across chains?'),
            PaperQuestion('Methods', 'Which backbone features are encoded?'),
            PaperQuestion('Methods', 'Why random decoding vs N-to-C?'),
            PaperQuestion('Methods', 'What Rosetta benchmark anchors it?'),
            PaperQuestion('Methods', 'How are interfaces/symmetry sampled?'),
            PaperQuestion('Methods', 'Which experiments validate designs?'),
        ),
    ),
    Mission(
        key='rfdiffusion',
        title='RFdiffusion',
        source='Mission paper: Watson et al., Nature 2023',
        prompt=(
            'Answer the 10 paper questions. Focus on how RFdiffusion turns '
            'protein structure prediction into a conditional backbone generator.'
        ),
        key_facts=(
            KeyFact('fine-tunes RoseTTAFold as a denoising model', ('rosettafold', 'fine-tune', 'fine tune', 'denoising')),
            KeyFact('generates protein backbones from noise', ('backbone', 'random noise', 'diffusion', 'denoise')),
            KeyFact('uses residue frames and 3D geometry', ('residue frame', 'c-alpha', 'ca coordinate', 'orientation', 'rigid')),
            KeyFact('uses iterative diffusion trajectories', ('200 steps', 'timestep', 'trajectory', 'iterative')),
            KeyFact('uses self-conditioning or previous predictions', ('self-conditioning', 'self conditioning', 'previous prediction', 'template')),
            KeyFact('supports unconditional and topology-constrained monomers', ('unconditional', 'topology', 'monomer', 'constrained')),
            KeyFact('supports binder and symmetric oligomer design', ('binder', 'symmetric', 'oligomer', 'symmetry')),
            KeyFact('supports motif or active-site scaffolding', ('motif', 'active site', 'enzyme', 'scaffolding')),
            KeyFact('was experimentally characterized', ('experimental', 'characterized', 'cryo-em', 'cryoem', 'x-ray')),
            KeyFact('can design from simple molecular specifications', ('specification', 'conditioning', 'target', 'molecular')),
        ),
        reward_item='rfdiffusion_crystal',
        reward_name='RFdiffusion Crystal',
        badge='Protein Design',
        xp=reward_xp(8, has_questions=True),
        gold=reward_gold(reward_xp(8, has_questions=True)),
        artifact_description=(
            'A crystal artifact for generative protein backbones: diffusion, '
            'conditioning, motif scaffolding, binders, and validation.'
        ),
        required_hits=8,
        questions=(
            PaperQuestion('Conceptual', 'What gap in protein design does RFdiffusion address?'),
            PaperQuestion('Conceptual', 'Why are diffusion models useful for backbones?'),
            PaperQuestion('Conceptual', 'Why adapt RoseTTAFold for generation?'),
            PaperQuestion('Conceptual', 'Which design tasks fit one framework?'),
            PaperQuestion('Conceptual', 'Why does experimental validation matter here?'),
            PaperQuestion('Methods', 'What residue-frame geometry is denoised?'),
            PaperQuestion('Methods', 'How are translations and rotations noised?'),
            PaperQuestion('Methods', 'What happens during a 200-step trajectory?'),
            PaperQuestion('Methods', 'What is self-conditioning in this model?'),
            PaperQuestion('Methods', 'Which experiments support the designs?'),
        ),
    ),
    Mission(
        key='free-tailed-bat',
        title='Free-tailed Bat Field Note',
        source='Field note: Mexican/Brazilian free-tailed bat ecology',
        prompt=(
            'Explain what makes a free-tailed bat distinctive. Include its tail, '
            'diet, roosting or migration behavior, and one reason it matters.'
        ),
        key_facts=(
            KeyFact('scientific name is Tadarida brasiliensis', ('tadarida', 'brasiliensis', 'mexican free-tailed', 'brazilian free-tailed')),
            KeyFact('tail extends beyond the tail membrane', ('free tail', 'free-tailed', 'tail membrane', 'uropatagium', 'extends beyond')),
            KeyFact('they eat flying insects and moths', ('insect', 'moth', 'beetle', 'fly', 'pest')),
            KeyFact('they hunt with echolocation', ('echolocation', 'echo', 'calls', 'sonar')),
            KeyFact('they roost in large colonies', ('colony', 'colonies', 'roost', 'cave', 'bridge', 'building')),
            KeyFact('many populations migrate seasonally', ('migrate', 'migration', 'winter', 'mexico', 'brazil')),
            KeyFact('they are fast long-winged fliers', ('fast', 'speed', 'long wings', 'narrow wings', '60 miles')),
            KeyFact('they help reduce crop pests', ('crop', 'agricultural', 'pesticide', 'farmers', 'pest control')),
        ),
        reward_item='free_tailed_bat',
        reward_name='Free-tailed Bat',
        badge='Animals',
        xp=reward_xp(4),
        gold=reward_gold(reward_xp(4)),
        artifact_description=(
            'A free-tailed bat artifact for animal biology: tail anatomy, insect '
            'hunting, colony roosting, migration, and ecosystem pest control.'
        ),
        required_hits=4,
    ),
)

MISSIONS = tuple(
    mission for mission in MISSION_LIBRARY
    if mission.key in STARTER_MISSION_KEYS
)

if len(MISSIONS) != len(STARTER_MISSION_KEYS):
    missing_keys = set(STARTER_MISSION_KEYS) - {mission.key for mission in MISSIONS}
    raise RuntimeError(f'Missing starter mission definitions: {sorted(missing_keys)}')


FIELD_PALETTES = {
    'Ecology': {
        'body': (96, 122, 73),
        'lid': (121, 154, 91),
        'trim': (51, 78, 52),
        'accent': (168, 205, 116),
        'glow': (197, 231, 137, 90),
    },
    'Animals': {
        'body': (94, 75, 103),
        'lid': (124, 96, 128),
        'trim': (53, 42, 68),
        'accent': (189, 151, 194),
        'glow': (204, 166, 220, 85),
    },
    'Neuroscience': {
        'body': (122, 90, 59),
        'lid': (158, 111, 72),
        'trim': (74, 50, 38),
        'accent': (237, 178, 72),
        'glow': (255, 218, 125, 90),
    },
    'Protein Design': {
        'body': (61, 100, 128),
        'lid': (78, 129, 159),
        'trim': (36, 59, 84),
        'accent': (111, 195, 203),
        'glow': (128, 225, 218, 85),
    },
    'Research Methods': {
        'body': (129, 78, 58),
        'lid': (164, 98, 68),
        'trim': (79, 45, 38),
        'accent': (234, 191, 89),
        'glow': (255, 224, 125, 90),
    },
    'Aging': {
        'body': (100, 104, 86),
        'lid': (132, 137, 106),
        'trim': (60, 66, 52),
        'accent': (210, 194, 111),
        'glow': (228, 213, 126, 85),
    },
    'Computational Neuroscience': {
        'body': (72, 85, 127),
        'lid': (96, 111, 156),
        'trim': (42, 48, 82),
        'accent': (155, 185, 238),
        'glow': (165, 197, 255, 85),
    },
    'BCI': {
        'body': (58, 99, 112),
        'lid': (76, 132, 147),
        'trim': (34, 61, 70),
        'accent': (236, 188, 91),
        'glow': (137, 225, 226, 86),
    },
    'Cognitive Science': {
        'body': (92, 88, 122),
        'lid': (119, 112, 151),
        'trim': (49, 46, 78),
        'accent': (214, 176, 98),
        'glow': (232, 198, 124, 88),
    },
    'Machine Learning': {
        'body': (79, 90, 99),
        'lid': (111, 122, 126),
        'trim': (42, 50, 56),
        'accent': (231, 176, 82),
        'glow': (241, 203, 112, 90),
    },
    'Collection': {
        'body': (131, 78, 40),
        'lid': (155, 91, 45),
        'trim': (72, 43, 28),
        'accent': (226, 176, 72),
        'glow': (252, 220, 120, 90),
    },
}


def field_palette(field):
    return FIELD_PALETTES.get(field, FIELD_PALETTES['Collection'])


def draw_artifact_emblem(surf, center, item, accent):
    cx, cy = center
    pygame.draw.circle(surf, (242, 221, 154), center, 8)
    pygame.draw.circle(surf, (57, 38, 29), center, 8, 2)

    ink = (34, 27, 25)
    if item == 'candlefish':
        pygame.draw.ellipse(surf, (94, 150, 162), (cx - 7, cy - 3, 12, 6))
        pygame.draw.polygon(surf, (50, 93, 112), [(cx + 4, cy), (cx + 9, cy - 4), (cx + 9, cy + 4)])
        pygame.draw.circle(surf, ink, (cx - 3, cy - 1), 1)
    elif item == 'memory_lantern':
        pygame.draw.rect(surf, (95, 61, 44), (cx - 4, cy - 6, 8, 12), border_radius=2)
        pygame.draw.rect(surf, (255, 211, 91), (cx - 2, cy - 3, 4, 7))
        pygame.draw.line(surf, ink, (cx - 4, cy - 6), (cx + 4, cy - 6), 1)
    elif item == 'research_compass':
        pygame.draw.circle(surf, (236, 210, 151), center, 5)
        pygame.draw.polygon(surf, (159, 58, 49), [(cx, cy - 5), (cx + 2, cy + 1), (cx - 1, cy + 1)])
        pygame.draw.polygon(surf, (41, 79, 99), [(cx, cy + 5), (cx - 2, cy - 1), (cx + 1, cy - 1)])
    elif item == 'program_map':
        pygame.draw.rect(surf, (226, 192, 122), (cx - 6, cy - 6, 12, 12))
        pygame.draw.line(surf, (91, 77, 105), (cx - 4, cy - 3), (cx + 4, cy - 3), 1)
        pygame.draw.line(surf, (91, 77, 105), (cx - 4, cy + 1), (cx + 4, cy + 1), 1)
        pygame.draw.rect(surf, (57, 111, 94), (cx - 4, cy - 4, 3, 3))
        pygame.draw.rect(surf, (57, 111, 94), (cx + 1, cy - 4, 3, 3))
        pygame.draw.rect(surf, (57, 111, 94), (cx - 4, cy + 2, 3, 3))
        pygame.draw.rect(surf, (57, 111, 94), (cx + 1, cy + 2, 3, 3))
    elif item == 'clone_graph':
        pygame.draw.circle(surf, (83, 78, 121), (cx - 5, cy - 4), 3)
        pygame.draw.circle(surf, (83, 78, 121), (cx - 5, cy + 4), 3)
        pygame.draw.circle(surf, (57, 111, 94), (cx + 4, cy - 5), 3)
        pygame.draw.circle(surf, (57, 111, 94), (cx + 5, cy + 4), 3)
        pygame.draw.line(surf, ink, (cx - 3, cy - 4), (cx + 2, cy - 5), 1)
        pygame.draw.line(surf, ink, (cx - 3, cy + 4), (cx + 3, cy + 4), 1)
        pygame.draw.line(surf, (198, 63, 72), (cx - 5, cy - 1), (cx - 5, cy + 1), 1)
        pygame.draw.line(surf, (236, 188, 91), (cx + 4, cy - 2), (cx + 5, cy + 1), 1)
    elif item == 'centaur_token':
        pygame.draw.circle(surf, (225, 187, 101), center, 6)
        pygame.draw.circle(surf, (96, 88, 130), center, 4)
        pygame.draw.line(surf, (240, 220, 148), (cx - 4, cy), (cx + 4, cy), 1)
        pygame.draw.line(surf, (240, 220, 148), (cx, cy - 4), (cx, cy + 4), 1)
        pygame.draw.circle(surf, (236, 218, 151), (cx - 2, cy - 2), 1)
        pygame.draw.circle(surf, (236, 218, 151), (cx + 2, cy + 2), 1)
    elif item == 'deep_q_core':
        pygame.draw.rect(surf, (47, 91, 105), (cx - 8, cy - 6, 16, 13), border_radius=2)
        pygame.draw.rect(surf, (235, 217, 143), (cx - 5, cy - 4, 10, 7), border_radius=1)
        pygame.draw.rect(surf, (66, 122, 139), (cx - 3, cy - 2, 3, 3))
        pygame.draw.rect(surf, (66, 122, 139), (cx + 2, cy - 2, 3, 3))
        pygame.draw.line(surf, (198, 63, 72), (cx - 5, cy + 4), (cx + 5, cy + 4), 1)
        pygame.draw.circle(surf, (236, 188, 91), (cx - 5, cy + 8), 1)
        pygame.draw.circle(surf, (133, 211, 211), (cx, cy + 9), 1)
        pygame.draw.circle(surf, (198, 63, 72), (cx + 5, cy + 8), 1)
    elif item == 'policy_value_stone':
        pygame.draw.circle(surf, (38, 38, 38), (cx - 3, cy), 6)
        pygame.draw.circle(surf, (238, 226, 178), (cx + 4, cy), 6)
        pygame.draw.circle(surf, (47, 91, 105), (cx - 3, cy), 2)
        pygame.draw.circle(surf, (198, 63, 72), (cx + 4, cy), 2)
        pygame.draw.line(surf, (236, 188, 91), (cx - 8, cy - 8), (cx + 9, cy + 8), 1)
        pygame.draw.line(surf, (133, 211, 211), (cx - 8, cy + 8), (cx + 9, cy - 8), 1)
        pygame.draw.rect(surf, (96, 62, 39), (cx - 9, cy - 9, 19, 19), 1)
    elif item == 'speech_decoder':
        pygame.draw.rect(surf, (47, 91, 105), (cx - 6, cy - 4, 12, 9), border_radius=2)
        pygame.draw.rect(surf, (235, 217, 143), (cx - 4, cy - 2, 8, 5))
        pygame.draw.line(surf, (48, 117, 133), (cx - 7, cy + 6), (cx + 7, cy + 6), 1)
        pygame.draw.line(surf, (48, 117, 133), (cx - 5, cy + 8), (cx + 5, cy + 8), 1)
        for dx, height in ((-5, 3), (-2, 6), (1, 4), (4, 7)):
            pygame.draw.line(surf, (198, 63, 72), (cx + dx, cy - height), (cx + dx, cy + height - 3), 1)
    elif item == 'rapid_speech_console':
        pygame.draw.rect(surf, (47, 91, 105), (cx - 7, cy - 6, 14, 12), border_radius=2)
        pygame.draw.rect(surf, (235, 217, 143), (cx - 5, cy - 4, 10, 7), border_radius=1)
        pygame.draw.line(surf, (198, 63, 72), (cx - 3, cy - 1), (cx - 1, cy - 3), 1)
        pygame.draw.line(surf, (198, 63, 72), (cx - 1, cy - 3), (cx + 2, cy + 1), 1)
        pygame.draw.line(surf, (48, 117, 133), (cx - 5, cy + 4), (cx + 5, cy + 4), 1)
        pygame.draw.circle(surf, (236, 188, 91), (cx - 5, cy + 7), 1)
        pygame.draw.circle(surf, (133, 211, 211), (cx, cy + 8), 1)
        pygame.draw.circle(surf, (236, 188, 91), (cx + 5, cy + 7), 1)
    elif item == 'handwriting_decoder':
        pygame.draw.rect(surf, (232, 208, 142), (cx - 6, cy - 6, 12, 12), border_radius=2)
        pygame.draw.line(surf, (73, 111, 139), (cx - 4, cy - 2), (cx + 4, cy - 2), 1)
        pygame.draw.line(surf, (73, 111, 139), (cx - 4, cy + 2), (cx + 2, cy + 2), 1)
        pygame.draw.line(surf, (198, 63, 72), (cx - 5, cy + 5), (cx + 4, cy - 4), 2)
        pygame.draw.circle(surf, (133, 211, 211), (cx + 6, cy - 6), 2)
    elif item == 'typing_neuroprosthesis':
        pygame.draw.rect(surf, (47, 91, 105), (cx - 8, cy - 5, 16, 10), border_radius=2)
        pygame.draw.rect(surf, (235, 217, 143), (cx - 6, cy - 3, 12, 6))
        for dx in (-4, 0, 4):
            pygame.draw.line(surf, (55, 86, 97), (cx + dx, cy - 3), (cx + dx, cy + 3), 1)
        pygame.draw.line(surf, (55, 86, 97), (cx - 6, cy), (cx + 6, cy), 1)
        pygame.draw.circle(surf, (198, 63, 72), (cx - 6, cy + 7), 1)
        pygame.draw.circle(surf, (133, 211, 211), (cx - 2, cy + 8), 1)
        pygame.draw.circle(surf, (198, 63, 72), (cx + 2, cy + 8), 1)
        pygame.draw.circle(surf, (133, 211, 211), (cx + 6, cy + 7), 1)
    elif item == 'neural_quadcopter':
        pygame.draw.circle(surf, (47, 91, 105), (cx, cy), 3)
        for dx, dy in ((-6, -5), (6, -5), (-6, 5), (6, 5)):
            pygame.draw.line(surf, (55, 86, 97), (cx, cy), (cx + dx, cy + dy), 1)
            pygame.draw.circle(surf, (133, 211, 211), (cx + dx, cy + dy), 3, 1)
            pygame.draw.circle(surf, (236, 188, 91), (cx + dx, cy + dy), 1)
        pygame.draw.polygon(surf, (198, 63, 72), [(cx, cy - 6), (cx + 3, cy - 1), (cx - 3, cy - 1)])
        pygame.draw.line(surf, (43, 34, 31), (cx - 4, cy + 8), (cx + 4, cy + 8), 1)
    elif item == 'refit_cursor':
        pygame.draw.circle(surf, (133, 211, 211), center, 7, 1)
        pygame.draw.circle(surf, (236, 188, 91), center, 3)
        pygame.draw.line(surf, (47, 91, 105), (cx - 8, cy), (cx + 8, cy), 1)
        pygame.draw.line(surf, (47, 91, 105), (cx, cy - 8), (cx, cy + 8), 1)
        pygame.draw.polygon(surf, (198, 63, 72), [(cx + 2, cy + 1), (cx + 9, cy + 4), (cx + 4, cy + 9)])
        pygame.draw.line(surf, (43, 34, 31), (cx - 5, cy + 10), (cx + 6, cy + 10), 1)
    elif item == 'robotic_arm':
        pygame.draw.rect(surf, (47, 91, 105), (cx - 7, cy - 6, 5, 10), border_radius=1)
        pygame.draw.rect(surf, (66, 122, 139), (cx - 2, cy - 3, 8, 4), border_radius=1)
        pygame.draw.rect(surf, (66, 122, 139), (cx + 4, cy, 4, 8), border_radius=1)
        pygame.draw.circle(surf, (236, 188, 91), (cx - 2, cy - 1), 2)
        pygame.draw.circle(surf, (236, 188, 91), (cx + 5, cy + 1), 2)
        pygame.draw.line(surf, (198, 63, 72), (cx + 7, cy + 7), (cx + 10, cy + 5), 1)
        pygame.draw.line(surf, (198, 63, 72), (cx + 7, cy + 7), (cx + 10, cy + 9), 1)
        pygame.draw.circle(surf, (133, 211, 211), (cx - 8, cy + 6), 2)
    elif item == 'seven_dof_neuroarm':
        pygame.draw.rect(surf, (43, 57, 69), (cx - 8, cy - 7, 5, 12), border_radius=1)
        pygame.draw.rect(surf, (66, 122, 139), (cx - 4, cy - 4, 9, 4), border_radius=1)
        pygame.draw.rect(surf, (86, 151, 164), (cx + 3, cy - 1, 5, 8), border_radius=1)
        pygame.draw.circle(surf, (236, 188, 91), (cx - 4, cy - 3), 2)
        pygame.draw.circle(surf, (236, 188, 91), (cx + 4, cy), 2)
        for dx, dy in ((-9, 7), (-6, 9), (-3, 10), (0, 10), (3, 9), (6, 7), (9, 5)):
            pygame.draw.circle(surf, (133, 211, 211), (cx + dx, cy + dy), 1)
        pygame.draw.line(surf, (198, 63, 72), (cx + 7, cy + 6), (cx + 10, cy + 3), 1)
        pygame.draw.line(surf, (198, 63, 72), (cx + 7, cy + 6), (cx + 11, cy + 7), 1)
        pygame.draw.line(surf, (43, 34, 31), (cx - 7, cy + 11), (cx + 7, cy + 11), 1)
    elif item == 'fes_ibci_sleeve':
        pygame.draw.rect(surf, (66, 122, 139), (cx - 8, cy - 3, 14, 8), border_radius=2)
        pygame.draw.rect(surf, (47, 91, 105), (cx + 2, cy - 7, 6, 15), border_radius=2)
        pygame.draw.circle(surf, (236, 188, 91), (cx - 5, cy - 1), 2)
        pygame.draw.circle(surf, (236, 188, 91), (cx, cy + 2), 2)
        pygame.draw.line(surf, (198, 63, 72), (cx - 8, cy - 7), (cx - 2, cy - 2), 1)
        pygame.draw.line(surf, (198, 63, 72), (cx - 2, cy - 2), (cx - 6, cy + 5), 1)
        pygame.draw.line(surf, (198, 63, 72), (cx - 6, cy + 5), (cx + 1, cy + 9), 1)
        pygame.draw.circle(surf, (133, 211, 211), (cx - 10, cy - 8), 2, 1)
        pygame.draw.line(surf, (43, 34, 31), (cx + 4, cy + 9), (cx + 10, cy + 9), 1)
    elif item == 'jpca_spindle':
        pygame.draw.circle(surf, (47, 91, 105), center, 8, 1)
        pygame.draw.arc(surf, (66, 122, 139), (cx - 9, cy - 7, 18, 14), 0.2, 4.8, 2)
        pygame.draw.arc(surf, (133, 211, 211), (cx - 8, cy - 8, 16, 16), 3.4, 6.0, 2)
        pygame.draw.circle(surf, (236, 188, 91), (cx - 4, cy - 2), 2)
        pygame.draw.circle(surf, (236, 188, 91), (cx + 4, cy + 3), 2)
        pygame.draw.line(surf, (198, 63, 72), (cx - 7, cy + 7), (cx + 7, cy - 7), 1)
        pygame.draw.line(surf, (43, 34, 31), (cx - 5, cy + 10), (cx + 5, cy + 10), 1)
    elif item == 'intrinsic_manifold_map':
        pygame.draw.polygon(surf, (236, 220, 149), [(cx - 9, cy + 4), (cx - 2, cy - 6), (cx + 9, cy - 3), (cx + 2, cy + 7)])
        pygame.draw.line(surf, (47, 91, 105), (cx - 8, cy + 4), (cx + 7, cy - 3), 1)
        pygame.draw.line(surf, (47, 91, 105), (cx - 3, cy - 5), (cx + 3, cy + 6), 1)
        pygame.draw.circle(surf, (198, 63, 72), (cx - 4, cy + 2), 2)
        pygame.draw.circle(surf, (236, 188, 91), (cx + 1, cy - 1), 2)
        pygame.draw.circle(surf, (133, 211, 211), (cx + 5, cy + 2), 2)
        pygame.draw.arc(surf, (66, 122, 139), (cx - 10, cy - 8, 20, 16), 0.1, 2.8, 1)
        pygame.draw.line(surf, (43, 34, 31), (cx - 6, cy + 9), (cx + 6, cy + 9), 1)
    elif item == 'qwerty_decoder':
        pygame.draw.rect(surf, (47, 91, 105), (cx - 7, cy - 5, 14, 11), border_radius=2)
        pygame.draw.rect(surf, (235, 217, 143), (cx - 5, cy - 3, 10, 6))
        for dx in (-4, 0, 4):
            pygame.draw.line(surf, (55, 86, 97), (cx + dx, cy - 3), (cx + dx, cy + 3), 1)
        pygame.draw.line(surf, (55, 86, 97), (cx - 5, cy), (cx + 5, cy), 1)
        pygame.draw.circle(surf, (198, 63, 72), (cx - 4, cy + 6), 1)
        pygame.draw.circle(surf, (133, 211, 211), (cx, cy + 7), 1)
        pygame.draw.circle(surf, (198, 63, 72), (cx + 4, cy + 6), 1)
    elif item == 'silent_speller':
        pygame.draw.rect(surf, (47, 91, 105), (cx - 7, cy - 6, 14, 12), border_radius=2)
        pygame.draw.rect(surf, (236, 220, 149), (cx - 5, cy - 4, 10, 7))
        pygame.draw.line(surf, (53, 83, 94), (cx - 3, cy - 4), (cx - 3, cy + 3), 1)
        pygame.draw.line(surf, (53, 83, 94), (cx + 1, cy - 4), (cx + 1, cy + 3), 1)
        pygame.draw.line(surf, (53, 83, 94), (cx - 5, cy), (cx + 5, cy), 1)
        pygame.draw.arc(surf, (198, 63, 72), (cx - 12, cy - 5, 6, 10), -1.1, 1.1, 1)
        pygame.draw.arc(surf, (198, 63, 72), (cx + 6, cy - 5, 6, 10), 2.0, 4.2, 1)
        pygame.draw.circle(surf, (133, 211, 211), (cx - 5, cy + 8), 1)
        pygame.draw.circle(surf, (236, 188, 91), (cx, cy + 9), 1)
        pygame.draw.circle(surf, (133, 211, 211), (cx + 5, cy + 8), 1)
    elif item == 'speech_avatar_rig':
        pygame.draw.rect(surf, (47, 91, 105), (cx - 7, cy - 7, 14, 13), border_radius=2)
        pygame.draw.rect(surf, (237, 219, 149), (cx - 5, cy - 5, 10, 8), border_radius=1)
        pygame.draw.circle(surf, (57, 103, 121), (cx - 2, cy - 1), 3)
        pygame.draw.circle(surf, (43, 34, 31), (cx - 3, cy - 2), 1)
        pygame.draw.circle(surf, (43, 34, 31), (cx + 1, cy - 2), 1)
        pygame.draw.line(surf, (198, 63, 72), (cx - 3, cy + 1), (cx + 2, cy + 1), 1)
        pygame.draw.arc(surf, (133, 211, 211), (cx + 5, cy - 6, 7, 7), -1.0, 1.2, 1)
        pygame.draw.arc(surf, (133, 211, 211), (cx + 6, cy - 2, 7, 7), -1.0, 1.2, 1)
        pygame.draw.circle(surf, (236, 188, 91), (cx - 5, cy + 7), 1)
        pygame.draw.circle(surf, (198, 63, 72), (cx, cy + 8), 1)
        pygame.draw.circle(surf, (133, 211, 211), (cx + 5, cy + 7), 1)
    elif item == 'tactile_feedback_glove':
        pygame.draw.rect(surf, (47, 91, 105), (cx - 6, cy - 3, 10, 8), border_radius=2)
        for dx in (-6, -3, 0, 3, 6):
            pygame.draw.line(surf, (235, 217, 143), (cx + dx, cy - 7), (cx + dx, cy - 2), 2)
            pygame.draw.circle(surf, (236, 188, 91), (cx + dx, cy - 8), 1)
        pygame.draw.circle(surf, (198, 63, 72), (cx - 3, cy + 1), 1)
        pygame.draw.circle(surf, (198, 63, 72), (cx + 2, cy + 2), 1)
        pygame.draw.arc(surf, (133, 211, 211), (cx + 4, cy - 2, 8, 8), -1.0, 1.2, 1)
        pygame.draw.arc(surf, (133, 211, 211), (cx + 6, cy, 8, 8), -1.0, 1.2, 1)
        pygame.draw.line(surf, (43, 34, 31), (cx - 5, cy + 5), (cx + 5, cy + 5), 1)
    elif item == 'object_touch_palette':
        pygame.draw.rect(surf, (47, 91, 105), (cx - 7, cy - 6, 14, 12), border_radius=2)
        pygame.draw.rect(surf, (235, 217, 143), (cx - 5, cy - 4, 10, 8), border_radius=1)
        pygame.draw.circle(surf, (198, 63, 72), (cx - 3, cy - 1), 2)
        pygame.draw.circle(surf, (236, 188, 91), (cx + 2, cy - 2), 2)
        pygame.draw.circle(surf, (133, 211, 211), (cx + 1, cy + 3), 2)
        pygame.draw.arc(surf, (133, 211, 211), (cx + 5, cy - 5, 7, 7), -1.0, 1.2, 1)
        pygame.draw.arc(surf, (198, 63, 72), (cx - 12, cy - 4, 7, 7), 2.0, 4.2, 1)
        pygame.draw.line(surf, (43, 34, 31), (cx - 5, cy + 6), (cx + 5, cy + 6), 1)
    elif item == 'protein_hunter_map':
        pygame.draw.rect(surf, (232, 201, 134), (cx - 5, cy - 5, 10, 10))
        pygame.draw.line(surf, (121, 76, 45), (cx - 3, cy - 2), (cx + 3, cy - 2), 1)
        pygame.draw.line(surf, (121, 76, 45), (cx - 2, cy + 1), (cx + 4, cy + 2), 1)
        pygame.draw.circle(surf, (47, 111, 78), (cx + 3, cy + 4), 1)
    elif item == 'mpnn_gear':
        pygame.draw.circle(surf, (128, 142, 151), center, 5)
        pygame.draw.circle(surf, ink, center, 2)
        for dx, dy in ((0, -7), (0, 7), (-7, 0), (7, 0)):
            pygame.draw.rect(surf, (77, 86, 93), (cx + dx - 1, cy + dy - 1, 2, 2))
    elif item == 'rfdiffusion_crystal':
        pygame.draw.polygon(surf, (119, 201, 206), [(cx, cy - 7), (cx + 6, cy - 1), (cx + 3, cy + 6), (cx - 4, cy + 5), (cx - 6, cy - 2)])
        pygame.draw.line(surf, (238, 226, 150), (cx - 1, cy - 5), (cx + 3, cy + 4), 1)
    elif item == 'ligand_key':
        pygame.draw.circle(surf, (92, 165, 181), (cx - 3, cy - 2), 4)
        pygame.draw.circle(surf, (242, 221, 154), (cx - 3, cy - 2), 2)
        pygame.draw.rect(surf, (221, 171, 79), (cx + 1, cy - 3, 8, 3))
        pygame.draw.rect(surf, (221, 171, 79), (cx + 6, cy, 3, 4))
        pygame.draw.rect(surf, (137, 78, 52), (cx + 2, cy + 1, 2, 2))
    elif item == 'ligandforge_peptide':
        points = [(cx - 7, cy + 4), (cx - 4, cy), (cx - 1, cy + 3), (cx + 2, cy - 2), (cx + 6, cy + 1)]
        pygame.draw.lines(surf, (42, 88, 120), False, points, 2)
        for px, py in points:
            pygame.draw.circle(surf, (113, 205, 200), (px, py), 2)
        pygame.draw.polygon(surf, (236, 189, 77), [(cx + 1, cy - 8), (cx + 5, cy - 4), (cx + 2, cy - 4), (cx + 5, cy)])
    elif item == 'pmhc_prism':
        pygame.draw.polygon(surf, (103, 184, 197), [(cx - 6, cy - 5), (cx + 2, cy - 8), (cx + 7, cy - 2), (cx, cy + 3)])
        pygame.draw.polygon(surf, (227, 188, 86), [(cx - 5, cy + 4), (cx + 6, cy + 2), (cx + 4, cy + 7), (cx - 7, cy + 7)])
        pygame.draw.line(surf, ink, (cx - 3, cy - 2), (cx + 4, cy + 4), 1)
        pygame.draw.circle(surf, (187, 55, 67), (cx - 6, cy - 7), 2)
        pygame.draw.circle(surf, (187, 55, 67), (cx + 8, cy + 5), 2)
    elif item == 'escape_compass':
        pygame.draw.circle(surf, (231, 176, 82), center, 6)
        pygame.draw.line(surf, (43, 65, 93), (cx - 6, cy), (cx + 6, cy), 1)
        pygame.draw.line(surf, (43, 65, 93), (cx, cy - 6), (cx, cy + 6), 1)
        pygame.draw.polygon(surf, (179, 62, 52), [(cx + 1, cy - 5), (cx + 4, cy + 1), (cx, cy)])
        pygame.draw.polygon(surf, (72, 130, 151), [(cx - 1, cy + 5), (cx - 4, cy - 1), (cx, cy)])
    elif item == 'free_tailed_bat':
        pygame.draw.polygon(surf, (52, 43, 58), [(cx, cy - 2), (cx - 8, cy - 5), (cx - 5, cy + 2), (cx, cy + 2)])
        pygame.draw.polygon(surf, (52, 43, 58), [(cx, cy - 2), (cx + 8, cy - 5), (cx + 5, cy + 2), (cx, cy + 2)])
        pygame.draw.rect(surf, (35, 28, 39), (cx - 2, cy - 3, 4, 7))
        pygame.draw.line(surf, ink, (cx, cy + 4), (cx, cy + 8), 1)
    else:
        pygame.draw.circle(surf, accent, center, 4)


def make_artifact_emblem(item, accent, size=42):
    base = pygame.Surface((24, 24), pygame.SRCALPHA)
    draw_artifact_emblem(base, (12, 12), item, accent)
    return pygame.transform.scale(base, (size, size))


class KnowledgeChest(pygame.sprite.Sprite):
    def __init__(self, pos, groups, mission_index=None):
        super().__init__(groups)
        self.mission_index = mission_index
        self.mission = MISSIONS[mission_index] if mission_index is not None else None
        self.opened = False
        self.closed_image = self.make_image(False)
        self.open_image = self.make_image(True)
        self.image = self.closed_image
        self.rect = self.image.get_rect(center=pos)
        self.z = LAYERS['main']
        self.hitbox = self.rect.copy().inflate(-16, -28)

    def chest_palette(self):
        field = self.mission.badge if self.mission else 'Collection'
        return field_palette(field)

    def set_open(self, opened):
        if self.opened == opened:
            return

        midbottom = self.rect.midbottom
        self.opened = opened
        self.image = self.open_image if opened else self.closed_image
        self.rect = self.image.get_rect(midbottom=midbottom)
        self.hitbox = self.rect.copy().inflate(-16, -28)

    def make_image(self, opened):
        palette = self.chest_palette()
        surf = pygame.Surface((72, 64), pygame.SRCALPHA)
        shadow = pygame.Rect(10, 52, 52, 8)
        pygame.draw.ellipse(surf, (34, 24, 20, 90), shadow)

        if opened:
            pygame.draw.polygon(surf, palette['glow'], [(36, 4), (68, 44), (4, 44)])
            pygame.draw.rect(surf, palette['body'], (13, 28, 46, 28), border_radius=4)
            pygame.draw.rect(surf, palette['trim'], (13, 28, 46, 28), width=3, border_radius=4)
            pygame.draw.polygon(surf, palette['lid'], [(14, 27), (56, 15), (58, 27)])
            pygame.draw.line(surf, palette['trim'], (14, 27), (56, 15), 3)
            pygame.draw.rect(surf, palette['accent'], (32, 37, 8, 10), border_radius=2)
            self.draw_reward_emblem(surf, (36, 23))
        else:
            pygame.draw.rect(surf, palette['body'], (12, 24, 48, 32), border_radius=4)
            pygame.draw.rect(surf, palette['trim'], (12, 24, 48, 32), width=3, border_radius=4)
            pygame.draw.rect(surf, palette['lid'], (16, 16, 40, 18), border_radius=7)
            pygame.draw.rect(surf, palette['trim'], (16, 16, 40, 18), width=3, border_radius=7)
            pygame.draw.rect(surf, palette['accent'], (32, 30, 8, 11), border_radius=2)
            self.draw_reward_emblem(surf, (36, 44))

        pygame.draw.rect(surf, palette['accent'], (14, 34, 44, 4))
        pygame.draw.circle(surf, palette['trim'], (36, 43), 2)
        return surf

    def draw_reward_emblem(self, surf, center):
        if self.mission:
            draw_artifact_emblem(
                surf,
                center,
                self.mission.reward_item,
                self.chest_palette()['accent'])
        else:
            cx, cy = center
            pygame.draw.circle(surf, (242, 221, 154), center, 8)
            pygame.draw.circle(surf, (57, 38, 29), center, 8, 2)
            pygame.draw.rect(surf, (104, 70, 43), (cx - 5, cy - 5, 10, 10), border_radius=2)
            pygame.draw.rect(surf, (232, 194, 93), (cx - 4, cy - 3, 8, 2))
            pygame.draw.rect(surf, (232, 194, 93), (cx - 4, cy + 2, 8, 2))


class KnowledgeCollectible(pygame.sprite.Sprite):
    def __init__(self, pos, groups, mission_index):
        super().__init__(groups)
        self.mission_index = mission_index
        self.mission = MISSIONS[mission_index]
        self.float_phase = mission_index * 0.8
        self.base_y = pos[1]
        self.image = self.make_image()
        self.rect = self.image.get_rect(center=pos)
        self.z = LAYERS['main']
        self.hitbox = self.rect.copy().inflate(-16, -18)

    def make_image(self):
        surf = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (34, 24, 20, 80), (12, 48, 40, 8))

        icon = KnowledgeJournal.make_item_icon(self.mission.reward_item)
        surf.blit(icon, icon.get_rect(center=(32, 30)))
        return surf

    def update(self, dt):
        self.float_phase += dt * 2.8
        self.rect.centery = self.base_y + int(math.sin(self.float_phase) * 3)
        self.hitbox.center = self.rect.center


class KnowledgeJournal:
    def __init__(self, player):
        self.display_surface = pygame.display.get_surface()
        self.player = player
        self.font = pygame.font.Font(get_path('../font/LycheeSoda.ttf'), 30)
        self.small_font = pygame.font.Font(get_path('../font/LycheeSoda.ttf'), 22)
        self.tiny_font = pygame.font.Font(get_path('../font/LycheeSoda.ttf'), 18)
        self.micro_font = pygame.font.Font(get_path('../font/LycheeSoda.ttf'), 15)
        self.nano_font = pygame.font.Font(get_path('../font/LycheeSoda.ttf'), 13)
        self.item_icons = {
            mission.reward_item: self.make_item_icon(mission.reward_item)
            for mission in MISSIONS
        }
        self.slot_surf = self.make_slot()

        self.missions = MISSIONS
        self.index = 0
        self.collection_index = 0
        self.active = False
        self.answer_mode = False
        self.collection_mode = False
        self.grading = False
        self.grade_queue = Queue()
        self.update_queue = Queue()
        self.update_check_started = False
        self.update_info = None
        self.update_popup_active = False
        self.submit_button_rect = None
        self.welcome_button_rect = None
        self.update_open_button_rect = None
        self.update_later_button_rect = None
        self.answer = ''
        self.messages = {}
        self.feedback = {}
        self.expanded_responses = set()
        self.question_scrolls = {}
        self.question_panel_rect = None
        self.question_max_scroll = 0
        self.daily_notice = ''
        self.ensure_player_state()
        self.load_daily_state()
        self.apply_daily_penalty()
        self.welcome_active = not self.player.welcome_seen
        self.start_update_check()

    def make_slot(self):
        surf = pygame.Surface((54, 54), pygame.SRCALPHA)
        pygame.draw.rect(surf, (112, 73, 42), (0, 0, 54, 54), border_radius=5)
        pygame.draw.rect(surf, (238, 205, 139), (4, 4, 46, 46), border_radius=4)
        pygame.draw.rect(surf, (78, 50, 33), (0, 0, 54, 54), 3, border_radius=5)
        pygame.draw.line(surf, (255, 233, 174), (8, 8), (46, 8), 2)
        pygame.draw.line(surf, (151, 98, 52), (8, 46), (46, 46), 2)
        return surf

    @staticmethod
    def make_item_icon(item_id):
        base = pygame.Surface((24, 24), pygame.SRCALPHA)

        def px(color, rect):
            pygame.draw.rect(base, color, rect)

        if item_id == 'candlefish':
            px((241, 229, 163), (3, 11, 3, 3))
            px((95, 141, 161), (5, 9, 11, 6))
            px((134, 185, 198), (7, 8, 8, 2))
            px((43, 82, 103), (9, 15, 7, 2))
            px((59, 104, 132), (16, 10, 4, 4))
            px((59, 104, 132), (18, 8, 3, 2))
            px((59, 104, 132), (18, 14, 3, 2))
            px((247, 198, 72), (8, 11, 3, 2))
            px((24, 32, 38), (14, 10, 1, 1))
            px((253, 232, 123), (6, 6, 2, 2))
            px((253, 232, 123), (3, 16, 2, 2))
        elif item_id == 'strawberry':
            px((51, 112, 57), (10, 3, 4, 2))
            px((74, 139, 69), (8, 5, 8, 3))
            px((187, 45, 58), (7, 8, 10, 3))
            px((220, 55, 67), (5, 10, 14, 5))
            px((199, 43, 55), (6, 15, 12, 3))
            px((157, 38, 47), (8, 18, 8, 2))
            px((249, 203, 118), (8, 11, 1, 1))
            px((249, 203, 118), (13, 12, 1, 1))
            px((249, 203, 118), (10, 15, 1, 1))
            px((249, 203, 118), (15, 16, 1, 1))
            px((114, 31, 39), (9, 20, 6, 1))
        elif item_id == 'memory_lantern':
            px((88, 53, 38), (8, 3, 8, 2))
            px((129, 81, 43), (6, 5, 12, 3))
            px((66, 43, 33), (7, 8, 2, 10))
            px((66, 43, 33), (15, 8, 2, 10))
            px((244, 176, 70), (9, 8, 6, 10))
            px((255, 226, 122), (10, 9, 4, 7))
            px((180, 95, 55), (8, 18, 8, 2))
            px((61, 96, 132), (11, 11, 2, 3))
            px((239, 206, 122), (5, 20, 14, 1))
        elif item_id == 'research_compass':
            px((72, 50, 42), (7, 3, 10, 2))
            px((98, 65, 43), (5, 5, 14, 14))
            px((236, 210, 151), (7, 7, 10, 10))
            px((36, 85, 102), (11, 8, 2, 2))
            px((36, 85, 102), (13, 10, 2, 2))
            px((168, 58, 45), (9, 13, 3, 3))
            px((168, 58, 45), (12, 12, 3, 2))
            px((43, 31, 26), (11, 4, 2, 2))
            px((43, 31, 26), (11, 18, 2, 2))
            px((43, 31, 26), (4, 11, 2, 2))
            px((43, 31, 26), (18, 11, 2, 2))
        elif item_id == 'program_map':
            px((116, 79, 48), (4, 5, 16, 14))
            px((229, 197, 126), (5, 4, 14, 14))
            px((164, 101, 58), (6, 7, 12, 1))
            px((164, 101, 58), (6, 12, 12, 1))
            px((72, 124, 98), (7, 8, 3, 3))
            px((72, 124, 98), (14, 8, 3, 3))
            px((72, 124, 98), (7, 13, 3, 3))
            px((72, 124, 98), (14, 13, 3, 3))
            px((83, 78, 121), (10, 9, 4, 1))
            px((83, 78, 121), (10, 14, 4, 1))
            px((64, 49, 75), (19, 7, 2, 8))
            px((238, 215, 143), (3, 17, 15, 2))
        elif item_id == 'clone_graph':
            px((53, 45, 76), (4, 5, 16, 14))
            px((231, 199, 130), (5, 4, 14, 14))
            px((82, 78, 124), (6, 7, 5, 5))
            px((103, 96, 151), (7, 6, 3, 3))
            px((82, 78, 124), (6, 14, 5, 5))
            px((103, 96, 151), (7, 13, 3, 3))
            px((57, 116, 98), (14, 6, 5, 5))
            px((80, 145, 117), (15, 5, 3, 3))
            px((57, 116, 98), (14, 14, 5, 5))
            px((80, 145, 117), (15, 13, 3, 3))
            px((44, 38, 55), (11, 9, 3, 1))
            px((44, 38, 55), (11, 16, 3, 1))
            px((198, 63, 72), (8, 11, 1, 3))
            px((236, 188, 91), (16, 11, 1, 3))
            px((64, 49, 75), (19, 8, 2, 7))
            px((238, 215, 143), (3, 17, 15, 2))
        elif item_id == 'centaur_token':
            px((85, 72, 111), (8, 4, 9, 2))
            px((126, 104, 153), (6, 6, 13, 12))
            px((227, 185, 94), (8, 5, 9, 13))
            px((244, 220, 143), (9, 7, 7, 9))
            px((92, 88, 132), (10, 8, 5, 6))
            px((51, 45, 76), (11, 9, 3, 4))
            px((238, 214, 135), (6, 11, 12, 1))
            px((238, 214, 135), (11, 6, 1, 12))
            px((244, 232, 169), (9, 8, 2, 2))
            px((244, 232, 169), (14, 13, 2, 2))
            px((59, 111, 116), (4, 17, 16, 2))
            px((35, 31, 53), (8, 19, 9, 1))
        elif item_id == 'deep_q_core':
            px((34, 53, 65), (4, 5, 16, 13))
            px((66, 122, 139), (5, 4, 14, 12))
            px((236, 220, 149), (7, 7, 10, 6))
            px((47, 91, 105), (8, 8, 3, 3))
            px((47, 91, 105), (13, 8, 3, 3))
            px((198, 57, 68), (7, 14, 10, 1))
            px((236, 188, 91), (5, 19, 2, 2))
            px((132, 211, 211), (11, 20, 2, 2))
            px((198, 57, 68), (17, 19, 2, 2))
            px((44, 37, 50), (8, 22, 8, 1))
        elif item_id == 'policy_value_stone':
            px((91, 61, 40), (4, 4, 16, 16))
            px((133, 91, 55), (5, 5, 14, 14))
            px((34, 34, 34), (7, 8, 7, 7))
            px((238, 225, 179), (11, 8, 7, 7))
            px((47, 91, 105), (9, 10, 3, 3))
            px((198, 57, 68), (13, 10, 3, 3))
            px((236, 188, 91), (5, 6, 13, 1))
            px((236, 188, 91), (6, 7, 11, 1))
            px((132, 211, 211), (6, 17, 12, 1))
            px((132, 211, 211), (5, 16, 14, 1))
            px((44, 37, 50), (8, 22, 8, 1))
        elif item_id == 'speech_decoder':
            px((35, 55, 67), (5, 5, 14, 10))
            px((65, 122, 139), (6, 4, 12, 10))
            px((238, 220, 146), (8, 7, 8, 5))
            px((43, 76, 92), (8, 15, 8, 2))
            px((235, 188, 91), (11, 17, 2, 4))
            px((198, 57, 68), (3, 9, 1, 5))
            px((198, 57, 68), (20, 8, 1, 7))
            px((229, 92, 88), (6, 10, 1, 3))
            px((229, 92, 88), (17, 9, 1, 5))
            px((133, 211, 211), (7, 19, 10, 1))
            px((44, 37, 50), (9, 21, 6, 1))
        elif item_id == 'rapid_speech_console':
            px((35, 55, 67), (4, 4, 16, 14))
            px((66, 122, 139), (5, 3, 14, 13))
            px((238, 220, 146), (7, 6, 10, 7))
            px((198, 57, 68), (8, 10, 2, 1))
            px((198, 57, 68), (10, 8, 2, 1))
            px((198, 57, 68), (12, 9, 2, 1))
            px((198, 57, 68), (14, 7, 2, 1))
            px((43, 76, 92), (7, 15, 10, 2))
            px((236, 188, 91), (5, 19, 2, 2))
            px((132, 211, 211), (11, 20, 2, 2))
            px((236, 188, 91), (17, 19, 2, 2))
            px((44, 37, 50), (8, 22, 8, 1))
        elif item_id == 'handwriting_decoder':
            px((78, 50, 33), (5, 4, 14, 16))
            px((236, 211, 145), (6, 3, 12, 16))
            px((249, 232, 170), (8, 5, 8, 10))
            px((61, 101, 129), (8, 7, 8, 1))
            px((61, 101, 129), (8, 10, 7, 1))
            px((61, 101, 129), (8, 13, 5, 1))
            px((193, 58, 69), (5, 17, 12, 2))
            px((221, 91, 86), (7, 15, 9, 2))
            px((238, 189, 89), (15, 12, 3, 3))
            px((133, 211, 211), (17, 4, 3, 3))
            px((45, 55, 68), (8, 20, 8, 1))
        elif item_id == 'typing_neuroprosthesis':
            px((35, 55, 67), (3, 6, 18, 12))
            px((66, 122, 139), (4, 5, 16, 11))
            px((236, 220, 149), (5, 7, 14, 7))
            px((51, 80, 91), (8, 7, 1, 7))
            px((51, 80, 91), (12, 7, 1, 7))
            px((51, 80, 91), (16, 7, 1, 7))
            px((51, 80, 91), (5, 10, 14, 1))
            px((51, 80, 91), (5, 13, 14, 1))
            px((245, 232, 169), (6, 8, 2, 1))
            px((245, 232, 169), (10, 8, 2, 1))
            px((245, 232, 169), (14, 8, 2, 1))
            px((198, 57, 68), (4, 19, 2, 2))
            px((133, 211, 211), (8, 20, 2, 2))
            px((198, 57, 68), (13, 20, 2, 2))
            px((133, 211, 211), (18, 19, 2, 2))
            px((44, 37, 50), (8, 22, 8, 1))
        elif item_id == 'neural_quadcopter':
            px((35, 55, 67), (10, 10, 4, 4))
            px((66, 122, 139), (9, 9, 6, 6))
            px((51, 80, 91), (6, 6, 12, 1))
            px((51, 80, 91), (6, 17, 12, 1))
            px((51, 80, 91), (6, 6, 1, 12))
            px((51, 80, 91), (17, 6, 1, 12))
            px((132, 211, 211), (3, 3, 5, 5))
            px((132, 211, 211), (16, 3, 5, 5))
            px((132, 211, 211), (3, 16, 5, 5))
            px((132, 211, 211), (16, 16, 5, 5))
            px((236, 188, 91), (5, 5, 1, 1))
            px((236, 188, 91), (18, 5, 1, 1))
            px((236, 188, 91), (5, 18, 1, 1))
            px((236, 188, 91), (18, 18, 1, 1))
            px((198, 57, 68), (11, 5, 2, 4))
            px((44, 37, 50), (8, 22, 8, 1))
        elif item_id == 'refit_cursor':
            px((35, 55, 67), (10, 4, 4, 16))
            px((35, 55, 67), (4, 10, 16, 4))
            px((132, 211, 211), (6, 6, 12, 2))
            px((132, 211, 211), (6, 16, 12, 2))
            px((132, 211, 211), (6, 8, 2, 8))
            px((132, 211, 211), (16, 8, 2, 8))
            px((236, 188, 91), (9, 9, 6, 6))
            px((248, 225, 145), (11, 10, 2, 2))
            px((198, 57, 68), (15, 14, 4, 3))
            px((198, 57, 68), (17, 16, 3, 4))
            px((235, 95, 90), (18, 15, 2, 2))
            px((44, 37, 50), (8, 22, 8, 1))
        elif item_id == 'robotic_arm':
            px((35, 55, 67), (4, 7, 5, 11))
            px((66, 122, 139), (8, 9, 7, 4))
            px((66, 122, 139), (13, 12, 4, 7))
            px((236, 188, 91), (7, 8, 3, 3))
            px((236, 188, 91), (14, 11, 3, 3))
            px((198, 57, 68), (17, 17, 4, 1))
            px((198, 57, 68), (17, 18, 3, 1))
            px((198, 57, 68), (17, 15, 3, 1))
            px((132, 211, 211), (3, 18, 4, 3))
            px((44, 37, 50), (7, 22, 10, 1))
        elif item_id == 'seven_dof_neuroarm':
            px((34, 52, 64), (4, 5, 5, 13))
            px((66, 122, 139), (8, 8, 8, 4))
            px((86, 151, 164), (14, 11, 5, 7))
            px((236, 188, 91), (7, 7, 3, 3))
            px((236, 188, 91), (15, 10, 3, 3))
            px((198, 57, 68), (18, 15, 4, 1))
            px((198, 57, 68), (18, 17, 4, 1))
            for x, y in ((3, 19), (6, 20), (9, 21), (12, 21), (15, 20), (18, 19), (20, 17)):
                px((132, 211, 211), (x, y, 2, 2))
            px((236, 220, 149), (4, 3, 14, 1))
            px((44, 37, 50), (7, 22, 10, 1))
        elif item_id == 'fes_ibci_sleeve':
            px((66, 122, 139), (4, 9, 13, 7))
            px((35, 55, 67), (14, 6, 5, 12))
            px((88, 151, 166), (5, 8, 10, 2))
            px((236, 188, 91), (6, 10, 3, 3))
            px((236, 188, 91), (11, 13, 3, 3))
            px((198, 57, 68), (4, 5, 2, 4))
            px((198, 57, 68), (6, 7, 2, 2))
            px((198, 57, 68), (5, 15, 2, 4))
            px((198, 57, 68), (8, 18, 7, 1))
            px((132, 211, 211), (2, 4, 3, 3))
            px((44, 37, 50), (8, 22, 9, 1))
        elif item_id == 'jpca_spindle':
            px((35, 55, 67), (10, 4, 4, 16))
            px((35, 55, 67), (4, 10, 16, 4))
            px((66, 122, 139), (6, 5, 12, 2))
            px((66, 122, 139), (5, 7, 2, 7))
            px((132, 211, 211), (16, 10, 2, 8))
            px((132, 211, 211), (7, 17, 10, 2))
            px((236, 188, 91), (7, 8, 3, 3))
            px((236, 188, 91), (14, 14, 3, 3))
            px((198, 57, 68), (5, 18, 3, 1))
            px((198, 57, 68), (8, 15, 3, 1))
            px((198, 57, 68), (11, 12, 3, 1))
            px((198, 57, 68), (14, 9, 3, 1))
            px((44, 37, 50), (8, 22, 8, 1))
        elif item_id == 'intrinsic_manifold_map':
            px((92, 66, 43), (6, 6, 12, 12))
            px((238, 221, 148), (5, 7, 14, 10))
            px((246, 232, 169), (7, 6, 10, 4))
            px((45, 76, 91), (5, 16, 14, 1))
            px((45, 76, 91), (9, 7, 1, 10))
            px((65, 122, 139), (7, 14, 3, 1))
            px((65, 122, 139), (10, 12, 3, 1))
            px((65, 122, 139), (13, 10, 3, 1))
            px((198, 57, 68), (7, 13, 3, 3))
            px((236, 188, 91), (11, 10, 3, 3))
            px((132, 211, 211), (15, 12, 3, 3))
            px((44, 37, 50), (8, 22, 8, 1))
        elif item_id == 'qwerty_decoder':
            px((37, 60, 70), (4, 6, 16, 11))
            px((68, 126, 143), (5, 5, 14, 10))
            px((236, 220, 149), (6, 7, 12, 6))
            px((51, 80, 91), (9, 7, 1, 6))
            px((51, 80, 91), (14, 7, 1, 6))
            px((51, 80, 91), (6, 10, 12, 1))
            px((245, 232, 169), (7, 8, 2, 1))
            px((245, 232, 169), (12, 8, 2, 1))
            px((245, 232, 169), (16, 11, 1, 1))
            px((200, 58, 69), (6, 18, 2, 2))
            px((133, 211, 211), (11, 18, 2, 2))
            px((200, 58, 69), (16, 18, 2, 2))
            px((44, 37, 50), (8, 21, 8, 1))
        elif item_id == 'silent_speller':
            px((34, 52, 64), (4, 5, 16, 13))
            px((66, 121, 139), (5, 4, 14, 12))
            px((235, 218, 145), (7, 7, 10, 6))
            px((51, 80, 91), (10, 7, 1, 6))
            px((51, 80, 91), (14, 7, 1, 6))
            px((51, 80, 91), (7, 10, 10, 1))
            px((244, 232, 169), (8, 8, 2, 1))
            px((244, 232, 169), (12, 8, 2, 1))
            px((244, 232, 169), (15, 11, 1, 1))
            px((194, 57, 68), (2, 8, 1, 6))
            px((225, 91, 87), (3, 6, 1, 3))
            px((194, 57, 68), (21, 8, 1, 6))
            px((225, 91, 87), (20, 6, 1, 3))
            px((132, 211, 211), (5, 19, 2, 2))
            px((234, 188, 91), (11, 20, 2, 2))
            px((132, 211, 211), (17, 19, 2, 2))
            px((42, 36, 49), (8, 22, 8, 1))
        elif item_id == 'speech_avatar_rig':
            px((34, 52, 64), (4, 4, 16, 15))
            px((66, 121, 139), (5, 3, 14, 14))
            px((236, 218, 145), (7, 6, 10, 8))
            px((83, 135, 151), (9, 7, 6, 6))
            px((43, 34, 31), (10, 8, 1, 1))
            px((43, 34, 31), (14, 8, 1, 1))
            px((198, 57, 68), (10, 12, 5, 1))
            px((133, 211, 211), (18, 6, 1, 2))
            px((133, 211, 211), (20, 7, 1, 3))
            px((133, 211, 211), (18, 11, 1, 2))
            px((133, 211, 211), (20, 12, 1, 3))
            px((234, 188, 91), (5, 19, 2, 2))
            px((198, 57, 68), (11, 20, 2, 2))
            px((132, 211, 211), (17, 19, 2, 2))
            px((42, 36, 49), (8, 22, 8, 1))
        elif item_id == 'tactile_feedback_glove':
            px((34, 52, 64), (5, 10, 13, 8))
            px((66, 121, 139), (6, 9, 11, 8))
            px((236, 218, 145), (4, 5, 2, 8))
            px((236, 218, 145), (7, 3, 2, 10))
            px((236, 218, 145), (10, 3, 2, 10))
            px((236, 218, 145), (13, 4, 2, 9))
            px((236, 218, 145), (16, 6, 2, 7))
            px((236, 188, 91), (4, 4, 2, 2))
            px((236, 188, 91), (7, 2, 2, 2))
            px((236, 188, 91), (10, 2, 2, 2))
            px((236, 188, 91), (13, 3, 2, 2))
            px((236, 188, 91), (16, 5, 2, 2))
            px((198, 57, 68), (8, 12, 2, 2))
            px((198, 57, 68), (13, 13, 2, 2))
            px((132, 211, 211), (19, 8, 1, 3))
            px((132, 211, 211), (21, 9, 1, 5))
            px((132, 211, 211), (19, 14, 1, 3))
            px((42, 36, 49), (7, 20, 9, 1))
        elif item_id == 'object_touch_palette':
            px((34, 52, 64), (4, 5, 16, 14))
            px((66, 121, 139), (5, 4, 14, 13))
            px((236, 218, 145), (7, 6, 10, 8))
            px((198, 57, 68), (8, 8, 3, 3))
            px((236, 188, 91), (13, 7, 3, 3))
            px((132, 211, 211), (12, 12, 3, 3))
            px((83, 135, 151), (7, 12, 2, 2))
            px((132, 211, 211), (19, 7, 1, 3))
            px((132, 211, 211), (21, 8, 1, 5))
            px((198, 57, 68), (2, 9, 1, 5))
            px((42, 36, 49), (8, 20, 8, 1))
        elif item_id == 'protein_hunter_map':
            px((107, 74, 42), (4, 5, 16, 14))
            px((232, 201, 134), (5, 4, 14, 14))
            px((152, 84, 38), (6, 7, 6, 2))
            px((152, 84, 38), (12, 10, 5, 2))
            px((152, 84, 38), (8, 13, 8, 2))
            px((56, 99, 127), (15, 5, 3, 3))
            px((47, 111, 78), (5, 17, 12, 2))
            px((249, 232, 157), (18, 15, 2, 3))
        elif item_id == 'mpnn_gear':
            px((69, 72, 78), (10, 3, 4, 18))
            px((69, 72, 78), (3, 10, 18, 4))
            px((69, 72, 78), (6, 6, 12, 12))
            px((135, 145, 150), (8, 8, 8, 8))
            px((42, 50, 55), (10, 10, 4, 4))
            px((72, 124, 155), (4, 4, 3, 3))
            px((72, 124, 155), (17, 4, 3, 3))
            px((72, 124, 155), (4, 17, 3, 3))
            px((72, 124, 155), (17, 17, 3, 3))
        elif item_id == 'rfdiffusion_crystal':
            px((58, 62, 93), (10, 3, 5, 3))
            px((78, 115, 148), (7, 6, 10, 4))
            px((98, 162, 181), (5, 10, 14, 6))
            px((150, 219, 207), (7, 12, 9, 4))
            px((62, 91, 136), (8, 16, 8, 4))
            px((236, 219, 139), (15, 5, 3, 3))
            px((236, 219, 139), (4, 17, 3, 3))
            px((31, 42, 62), (10, 20, 6, 1))
        elif item_id == 'ligand_key':
            px((48, 93, 108), (4, 8, 8, 8))
            px((97, 173, 188), (5, 7, 6, 8))
            px((235, 217, 143), (7, 10, 2, 2))
            px((191, 121, 55), (11, 10, 10, 3))
            px((228, 170, 75), (11, 8, 9, 3))
            px((191, 121, 55), (18, 12, 2, 5))
            px((191, 121, 55), (15, 12, 2, 3))
            px((235, 217, 143), (13, 7, 3, 1))
            px((52, 79, 93), (4, 16, 9, 2))
            px((142, 73, 58), (16, 16, 4, 2))
            px((245, 218, 119), (20, 9, 2, 2))
            px((68, 124, 139), (3, 5, 3, 3))
        elif item_id == 'ligandforge_peptide':
            px((33, 52, 72), (4, 15, 4, 2))
            px((33, 52, 72), (7, 11, 4, 2))
            px((33, 52, 72), (10, 14, 4, 2))
            px((33, 52, 72), (13, 9, 4, 2))
            px((33, 52, 72), (16, 12, 4, 2))
            px((93, 184, 190), (3, 14, 4, 4))
            px((116, 212, 202), (7, 10, 4, 4))
            px((93, 184, 190), (10, 13, 4, 4))
            px((116, 212, 202), (13, 8, 4, 4))
            px((93, 184, 190), (17, 11, 4, 4))
            px((234, 188, 80), (12, 3, 3, 5))
            px((248, 223, 120), (15, 6, 3, 3))
            px((190, 126, 53), (13, 9, 4, 2))
            px((39, 75, 104), (7, 18, 10, 2))
            px((245, 228, 146), (5, 6, 2, 2))
            px((245, 228, 146), (19, 17, 2, 2))
        elif item_id == 'pmhc_prism':
            px((46, 76, 91), (6, 8, 12, 7))
            px((87, 164, 182), (7, 6, 9, 8))
            px((124, 207, 202), (10, 5, 5, 5))
            px((235, 192, 89), (5, 15, 13, 4))
            px((193, 123, 58), (6, 19, 11, 2))
            px((227, 218, 151), (8, 16, 8, 1))
            px((48, 55, 63), (11, 8, 2, 10))
            px((187, 55, 67), (3, 5, 3, 3))
            px((220, 79, 80), (4, 4, 2, 2))
            px((187, 55, 67), (18, 16, 3, 3))
            px((220, 79, 80), (19, 15, 2, 2))
            px((48, 93, 108), (3, 20, 16, 1))
        elif item_id == 'escape_compass':
            px((62, 73, 83), (8, 3, 8, 2))
            px((92, 103, 110), (5, 5, 14, 14))
            px((226, 185, 95), (7, 7, 10, 10))
            px((42, 52, 61), (11, 4, 2, 2))
            px((42, 52, 61), (11, 18, 2, 2))
            px((42, 52, 61), (4, 11, 2, 2))
            px((42, 52, 61), (18, 11, 2, 2))
            px((54, 94, 126), (6, 11, 12, 2))
            px((54, 94, 126), (11, 6, 2, 12))
            px((180, 62, 52), (12, 8, 4, 5))
            px((230, 91, 70), (13, 7, 2, 3))
            px((54, 129, 151), (8, 13, 4, 4))
            px((33, 42, 50), (10, 20, 5, 1))
        elif item_id == 'prediction_lens':
            px((38, 47, 78), (5, 8, 14, 9))
            px((73, 98, 147), (6, 7, 12, 9))
            px((149, 202, 224), (8, 8, 7, 6))
            px((224, 238, 203), (10, 10, 3, 2))
            px((43, 38, 63), (3, 11, 3, 3))
            px((43, 38, 63), (18, 11, 3, 3))
            px((241, 197, 76), (11, 3, 2, 4))
            px((241, 197, 76), (12, 4, 3, 2))
            px((99, 159, 176), (7, 18, 3, 2))
            px((99, 159, 176), (11, 19, 3, 2))
            px((99, 159, 176), (15, 18, 3, 2))
            px((244, 226, 143), (19, 5, 2, 2))
            px((244, 226, 143), (4, 19, 2, 2))
        elif item_id == 'free_tailed_bat':
            px((45, 36, 48), (10, 9, 5, 6))
            px((73, 61, 79), (8, 7, 3, 5))
            px((73, 61, 79), (14, 7, 3, 5))
            px((35, 28, 39), (3, 8, 7, 3))
            px((35, 28, 39), (15, 8, 7, 3))
            px((52, 43, 58), (1, 11, 8, 3))
            px((52, 43, 58), (16, 11, 8, 3))
            px((77, 69, 90), (5, 14, 5, 2))
            px((77, 69, 90), (14, 14, 5, 2))
            px((27, 22, 31), (11, 6, 2, 2))
            px((27, 22, 31), (14, 6, 2, 2))
            px((145, 121, 97), (12, 11, 1, 1))
            px((145, 121, 97), (15, 11, 1, 1))
            px((32, 25, 35), (12, 15, 2, 5))
            px((32, 25, 35), (13, 20, 1, 3))
        else:
            px((98, 65, 43), (5, 5, 14, 14))
            px((238, 205, 139), (8, 8, 8, 8))

        return pygame.transform.scale(base, (48, 48))

    def ensure_player_state(self):
        if not hasattr(self.player, 'knowledge_inventory'):
            self.player.knowledge_inventory = {}
        if not hasattr(self.player, 'knowledge_badges'):
            self.player.knowledge_badges = []
        if not hasattr(self.player, 'knowledge_xp'):
            self.player.knowledge_xp = 0
        if not hasattr(self.player, 'completed_missions'):
            self.player.completed_missions = set()
        if not hasattr(self.player, 'mission_responses'):
            self.player.mission_responses = {}
        if not hasattr(self.player, 'artifact_records'):
            self.player.artifact_records = {}
        if not hasattr(self.player, 'research_health'):
            self.player.research_health = MAX_RESEARCH_HEALTH
        if not hasattr(self.player, 'paper_read_dates'):
            self.player.paper_read_dates = set()
        if not hasattr(self.player, 'last_daily_check_date'):
            self.player.last_daily_check_date = None
        if not hasattr(self.player, 'daily_reward_inventory'):
            self.player.daily_reward_inventory = {}
        if not hasattr(self.player, 'welcome_seen'):
            self.player.welcome_seen = False
        if not hasattr(self.player, 'dismissed_update_version'):
            self.player.dismissed_update_version = ''

    def load_daily_state(self):
        if not STATE_PATH.exists():
            return

        try:
            data = json.loads(STATE_PATH.read_text())
        except (OSError, json.JSONDecodeError):
            self.daily_notice = 'Could not load research log.'
            return

        self.player.knowledge_inventory = data.get('knowledge_inventory', self.player.knowledge_inventory)
        self.player.knowledge_badges = data.get('knowledge_badges', self.player.knowledge_badges)
        self.player.knowledge_xp = int(data.get('knowledge_xp', self.player.knowledge_xp))
        self.player.completed_missions = set(data.get('completed_missions', self.player.completed_missions))
        self.player.mission_responses = data.get('mission_responses', self.player.mission_responses)
        self.player.artifact_records = data.get('artifact_records', self.player.artifact_records)
        self.player.research_health = int(data.get('research_health', self.player.research_health))
        self.player.paper_read_dates = set(data.get('paper_read_dates', self.player.paper_read_dates))
        self.player.last_daily_check_date = data.get('last_daily_check_date', self.player.last_daily_check_date)
        self.player.welcome_seen = bool(data.get('welcome_seen', self.player.welcome_seen))
        self.player.dismissed_update_version = str(data.get(
            'dismissed_update_version',
            self.player.dismissed_update_version))
        self.reconcile_progress_state()

    def save_daily_state(self):
        data = {
            'knowledge_inventory': self.player.knowledge_inventory,
            'knowledge_badges': self.player.knowledge_badges,
            'knowledge_xp': self.player.knowledge_xp,
            'completed_missions': sorted(self.player.completed_missions),
            'mission_responses': self.player.mission_responses,
            'artifact_records': self.player.artifact_records,
            'research_health': self.player.research_health,
            'paper_read_dates': sorted(self.player.paper_read_dates),
            'last_daily_check_date': self.player.last_daily_check_date,
            'welcome_seen': self.player.welcome_seen,
            'dismissed_update_version': self.player.dismissed_update_version,
        }
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(json.dumps(data, indent=2) + '\n')
        except OSError:
            self.daily_notice = 'Could not save research log.'

    def reconcile_progress_state(self):
        active_keys = {mission.key for mission in self.missions}
        active_items = {mission.reward_item for mission in self.missions}
        completed = set(self.player.completed_missions) & active_keys
        self.player.completed_missions = completed
        self.player.knowledge_inventory = {
            item: amount for item, amount in self.player.knowledge_inventory.items()
            if item in active_items
        }
        self.player.mission_responses = {
            key: response for key, response in self.player.mission_responses.items()
            if key in active_keys
        }
        self.player.artifact_records = {
            key: record for key, record in self.player.artifact_records.items()
            if key in active_keys and key in completed
        }
        self.player.knowledge_xp = sum(
            mission.xp for mission in self.missions
            if mission.key in completed)
        self.player.knowledge_badges = []
        for mission in self.missions:
            if mission.key in completed and mission.badge not in self.player.knowledge_badges:
                self.player.knowledge_badges.append(mission.badge)
            if mission.key in completed:
                self.ensure_artifact_record(mission)

    def ensure_artifact_record(self, mission):
        response = self.player.mission_responses.get(mission.key, {})
        record = self.player.artifact_records.setdefault(mission.key, {})
        record['reward_item'] = mission.reward_item
        record['reward_name'] = mission.reward_name
        record['field'] = mission.badge
        record['xp'] = mission.xp
        record['gold'] = mission.gold
        record.setdefault('collected_at', response.get('updated_at') or 'Before chest log')
        return record

    def apply_daily_penalty(self):
        today = date.today()
        last_check = self.parse_date(self.player.last_daily_check_date)
        if last_check is None:
            self.player.last_daily_check_date = today.isoformat()
            self.save_daily_state()
            return

        missed_days = 0
        checked_day = last_check
        while checked_day < today:
            if checked_day.isoformat() not in self.player.paper_read_dates:
                missed_days += 1
            checked_day += timedelta(days=1)

        if missed_days:
            loss = min(missed_days, self.player.research_health)
            self.player.research_health -= loss
            self.daily_notice = f'Missed {missed_days} daily paper{"s" if missed_days != 1 else ""}: -{loss} Research HP.'

        self.player.last_daily_check_date = today.isoformat()
        self.save_daily_state()

    def parse_date(self, value):
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def mark_paper_read(self):
        today = date.today().isoformat()
        already_read = today in self.player.paper_read_dates
        self.player.paper_read_dates.add(today)
        if not already_read and self.player.research_health < MAX_RESEARCH_HEALTH:
            self.player.research_health += 1
            self.daily_notice = 'Daily paper logged: +1 Research HP.'
            return 'Daily paper logged, +1 Research HP.'

        self.daily_notice = 'Daily paper logged for today.'
        return 'Daily paper logged for today.'

    def chest_inventory(self):
        inventory = dict(self.player.knowledge_inventory)
        for item, amount in getattr(self.player, 'daily_reward_inventory', {}).items():
            if amount:
                inventory[item] = inventory.get(item, 0) + amount
        return inventory

    def skill_xp(self, skill):
        total = 0
        for mission_key in self.player.completed_missions:
            mission = next((item for item in self.missions if item.key == mission_key), None)
            if mission and mission.badge == skill:
                total += mission.xp
        return total

    def skill_label(self, skill, include_xp=False):
        xp = self.skill_xp(skill)
        level = max(1, xp // SKILL_LEVEL_XP + 1)
        if include_xp:
            return f'{skill} Lv {level} ({xp} XP)'
        return f'{skill} Lv {level}'

    def collected_missions(self):
        completed = set(self.player.completed_missions)
        inventory = self.chest_inventory()
        return [
            mission for mission in self.missions
            if mission.key in completed and inventory.get(mission.reward_item, 0) > 0
        ]

    def selected_collection_mission(self):
        collected = self.collected_missions()
        if not collected:
            return None
        self.collection_index %= len(collected)
        return collected[self.collection_index]

    def first_unfinished_mission_index(self):
        for index, mission in enumerate(self.missions):
            if mission.key not in self.player.completed_missions:
                return index
        return 0

    def ordered_mission_indices(self):
        completed = set(self.player.completed_missions)
        return sorted(
            range(len(self.missions)),
            key=lambda index: (self.missions[index].key in completed, index))

    def mission_order_position(self, mission_index=None):
        order = self.ordered_mission_indices()
        if not order:
            return 0

        target_index = self.index if mission_index is None else mission_index
        try:
            return order.index(target_index)
        except ValueError:
            return 0

    def select_ordered_mission(self, step):
        order = self.ordered_mission_indices()
        if not order:
            return

        current_pos = self.mission_order_position()
        self.select_mission(order[(current_pos + step) % len(order)])

    def handle_mission_navigation_key(self, event):
        if event.key == pygame.K_UP or (not self.answer_mode and event.key == pygame.K_w):
            self.select_ordered_mission(-1)
            return True

        if event.key == pygame.K_DOWN or (not self.answer_mode and event.key == pygame.K_s):
            self.select_ordered_mission(1)
            return True

        return False

    def open_mission(self, index):
        self.collection_mode = False
        self.select_mission(index, keep_answer=False)
        self.active = True
        self.answer_mode = True
        self.answer = ''
        mission = self.missions[self.index]
        if mission.key in self.player.completed_missions:
            self.set_feedback(f'{mission.reward_name} is already in your collection. Submit again to update your saved response.')
        else:
            self.set_feedback('Type an answer, then press Enter to let the grader check it.')

    def open_collection(self):
        self.ensure_player_state()
        self.reconcile_progress_state()
        self.active = True
        self.answer_mode = False
        self.collection_mode = True
        self.answer = ''
        collected = self.collected_missions()
        if collected:
            self.collection_index = max(0, min(self.collection_index, len(collected) - 1))
        else:
            self.collection_index = 0

    def select_mission(self, index, keep_answer=True):
        new_index = max(0, min(index, len(self.missions) - 1))
        if new_index != self.index and not keep_answer:
            self.answer = ''
        elif new_index != self.index:
            self.answer_mode = False
            self.answer = ''
        self.index = new_index

    def set_feedback(self, message, detail=''):
        mission = self.missions[self.index]
        self.messages[mission.key] = message
        self.feedback[mission.key] = detail

    def current_feedback(self):
        mission = self.missions[self.index]
        message = self.messages.get(mission.key)
        detail = self.feedback.get(mission.key, '')

        if self.grading:
            return 'Grading your answer...', 'Please wait; the result will save automatically.'

        if message is None:
            if mission.key in self.player.completed_missions:
                message = f'{mission.reward_name} is already in your collection.'
            elif self.answer_mode:
                message = 'Type an answer, then press Enter to let the grader check it.'
            else:
                message = 'Press Enter to start this research challenge.'

        return message, detail

    def start_update_check(self):
        if self.update_check_started:
            return

        self.update_check_started = True
        Thread(target=self.update_check_worker, daemon=True).start()

    def update_check_worker(self):
        self.update_queue.put(read_latest_update())

    def poll_update_result(self):
        try:
            update_info = self.update_queue.get_nowait()
        except Empty:
            return

        if update_info and update_info.version != self.player.dismissed_update_version:
            self.update_info = update_info

    def activate_update_popup_if_ready(self):
        if (
                self.update_info and
                not self.update_popup_active and
                not self.active and
                not self.welcome_active and
                self.update_info.version != self.player.dismissed_update_version):
            self.update_popup_active = True

    def has_modal_popup(self):
        return self.welcome_active or self.update_popup_active

    def is_blocking(self):
        return self.welcome_active or self.update_popup_active or self.active

    def dismiss_welcome(self):
        self.welcome_active = False
        self.player.welcome_seen = True
        self.save_daily_state()

    def dismiss_update_popup(self):
        if self.update_info:
            self.player.dismissed_update_version = self.update_info.version
            self.save_daily_state()
        self.update_popup_active = False

    def open_update_page(self):
        if self.update_info and self.update_info.url:
            webbrowser.open(self.update_info.url)
        self.dismiss_update_popup()

    def is_complete_index(self, index):
        return self.missions[index].key in self.player.completed_missions

    def toggle(self):
        self.active = not self.active
        self.answer_mode = False
        self.collection_mode = False
        self.answer = ''
        if self.active and self.missions[self.index].key in self.player.completed_missions:
            self.select_mission(self.first_unfinished_mission_index(), keep_answer=False)

    def handle_event(self, event):
        if self.welcome_active:
            return self.handle_welcome_event(event)

        if self.update_popup_active:
            return self.handle_update_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN:
            return self.handle_mouse_event(event)

        if event.type == pygame.MOUSEWHEEL:
            return self.handle_scroll_event(event)

        if event.type == pygame.KEYUP:
            if self.active and self.answer_mode and not self.grading and event.key in SUBMIT_KEYS:
                self.start_submit_answer()
                return True
            return self.active

        if event.type == pygame.TEXTINPUT:
            if self.active and self.answer_mode and not self.grading:
                text = getattr(event, 'text', '')
                if text in ('\r', '\n'):
                    self.start_submit_answer()
                    return True
            return self.active

        if event.type != pygame.KEYDOWN:
            return self.active

        if event.key == pygame.K_j and not (self.active and self.answer_mode):
            self.toggle()
            return True

        if not self.active:
            return False

        if event.key == pygame.K_ESCAPE:
            self.active = False
            self.answer_mode = False
            self.collection_mode = False
            self.answer = ''
            return True

        if self.collection_mode:
            self.handle_collection_event(event)
            return True

        if self.grading:
            return True

        if self.handle_mission_navigation_key(event):
            return True

        if self.answer_mode:
            self.handle_answer_event(event)
            return True

        if event.key == pygame.K_e and not self.answer_mode:
            self.toggle_response_expansion()
            return True

        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.open_mission(self.index)

        return True

    def handle_welcome_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.welcome_button_rect and self.welcome_button_rect.collidepoint(event.pos):
                self.dismiss_welcome()
            return True

        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_ESCAPE):
            self.dismiss_welcome()
            return True

        return True

    def handle_update_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.update_open_button_rect and self.update_open_button_rect.collidepoint(event.pos):
                self.open_update_page()
            elif self.update_later_button_rect and self.update_later_button_rect.collidepoint(event.pos):
                self.dismiss_update_popup()
            return True

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.open_update_page()
                return True
            if event.key == pygame.K_ESCAPE:
                self.dismiss_update_popup()
                return True

        return True

    def handle_mouse_event(self, event):
        if not self.active:
            return False

        if (
                self.answer_mode and
                not self.grading and
                self.submit_button_rect and
                self.submit_button_rect.collidepoint(event.pos)):
            self.start_submit_answer()
            return True

        return self.active

    def handle_scroll_event(self, event):
        if not self.active or self.collection_mode:
            return False

        mission = self.missions[self.index]
        if not mission.questions:
            return self.active

        current = self.question_scrolls.get(mission.key, 0)
        next_scroll = current - event.y * 28
        self.question_scrolls[mission.key] = max(0, min(self.question_max_scroll, next_scroll))
        return True

    def handle_collection_event(self, event):
        collected = self.collected_missions()
        if not collected:
            return

        if event.key in (pygame.K_UP, pygame.K_w):
            self.collection_index = (self.collection_index - 1) % len(collected)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.collection_index = (self.collection_index + 1) % len(collected)

    def handle_answer_event(self, event):
        if self.grading:
            return

        if event.key == pygame.K_BACKSPACE:
            self.answer = self.answer[:-1]
        elif event.key in SUBMIT_KEYS or (event.key == pygame.K_s and event.mod & SUBMIT_MODS):
            self.start_submit_answer()
        elif event.key == pygame.K_TAB:
            remaining = MAX_ANSWER_CHARS - len(self.answer)
            self.answer += '    '[:remaining]
        else:
            typed = getattr(event, 'unicode', '')
            if typed and typed.isprintable() and len(self.answer) < MAX_ANSWER_CHARS:
                remaining = MAX_ANSWER_CHARS - len(self.answer)
                self.answer += typed[:remaining]

    def toggle_response_expansion(self):
        mission_key = self.missions[self.index].key
        if mission_key in self.expanded_responses:
            self.expanded_responses.remove(mission_key)
        elif mission_key in self.player.mission_responses:
            self.expanded_responses.add(mission_key)

    def save_response(self, mission, answer, result, feedback_detail=None):
        self.player.mission_responses[mission.key] = {
            'answer': answer.strip(),
            'passed': result.passed,
            'grader_response': feedback_detail or f'Grader: {result.response}',
            'grader': 'Grader',
            'hits': list(result.hits),
            'missing': list(result.missing),
            'updated_at': date.today().isoformat(),
        }

    def start_submit_answer(self):
        if self.grading:
            return

        mission = self.missions[self.index]
        submitted_answer = self.answer
        if not submitted_answer.strip():
            self.set_feedback('Write a few facts first, then submit.')
            return

        if not os.environ.get('OPENAI_API_KEY', '').strip():
            self.set_feedback(API_KEY_MISSING_MESSAGE)
            return

        self.grading = True
        self.set_feedback('Grading your answer...', 'Please wait; the result will save automatically.')
        Thread(
            target=self.grade_answer_worker,
            args=(mission, submitted_answer),
            daemon=True).start()

    def grade_answer_worker(self, mission, submitted_answer):
        try:
            result = self.grade_answer(mission, submitted_answer)
            self.grade_queue.put((mission.key, submitted_answer, result, None))
        except Exception as error:
            self.grade_queue.put((mission.key, submitted_answer, None, str(error)))

    def poll_grading_result(self):
        if not self.grading:
            return

        try:
            mission_key, submitted_answer, result, error = self.grade_queue.get_nowait()
        except Empty:
            return

        mission = next((item for item in self.missions if item.key == mission_key), None)
        self.grading = False
        if mission is None:
            return

        if error:
            self.set_feedback(API_KEY_MISSING_MESSAGE)
            return

        self.apply_grade_result(mission, submitted_answer, result)

    def submit_answer(self):
        mission = self.missions[self.index]
        submitted_answer = self.answer
        try:
            result = self.grade_answer(mission, submitted_answer)
        except GraderUnavailable:
            self.set_feedback(API_KEY_MISSING_MESSAGE)
            return
        self.apply_grade_result(mission, submitted_answer, result)

    def apply_grade_result(self, mission, submitted_answer, result):
        if mission.key in self.player.completed_missions:
            self.save_response(mission, submitted_answer, result)
            self.save_daily_state()
            self.answer_mode = False
            self.set_feedback(
                f'{mission.reward_name} is already in your collection.',
                f'Grader: {result.response}')
            return

        if result.passed:
            self.player.completed_missions.add(mission.key)
            self.player.knowledge_inventory[mission.reward_item] = (
                self.player.knowledge_inventory.get(mission.reward_item, 0) + 1
            )
            self.player.money += mission.gold
            self.reconcile_progress_state()
            artifact_record = self.ensure_artifact_record(mission)
            if artifact_record.get('collected_at') == 'Before chest log':
                artifact_record['collected_at'] = date.today().isoformat()
            skill_after = self.skill_label(mission.badge)
            self.answer_mode = False
            daily_detail = self.mark_paper_read() if mission.questions else ''
            detail = f'Grader: {result.response}'
            if daily_detail:
                detail += ' | ' + daily_detail
            self.save_response(mission, submitted_answer, result, detail)
            self.save_daily_state()
            self.set_feedback(
                f'Earned {mission.reward_name}, {skill_after}, +{mission.xp} XP.',
                detail)
        else:
            if result.grader == 'LLM grader':
                detail = f'Grader: {result.response}'
                self.save_response(mission, submitted_answer, result, detail)
                self.save_daily_state()
                self.set_feedback(
                    'The grader wants a stronger answer.',
                    detail)
            else:
                needed = max(0, mission.required_hits - len(result.hits))
                detail = f'Grader: {result.response}'
                self.save_response(mission, submitted_answer, result, detail)
                self.save_daily_state()
                self.set_feedback(
                    f'The grader needs {needed} more key fact{"s" if needed != 1 else ""}.',
                    detail)

    def grade_answer(self, mission, answer):
        return self.grade_answer_with_llm(mission, answer)

    def local_grade_answer(self, mission, answer):
        normalized = ' '.join(answer.lower().split())
        hits = []
        missing = []

        for fact in mission.key_facts:
            if any(keyword in normalized for keyword in fact.keywords):
                hits.append(fact.label)
            else:
                missing.append(fact.label)

        return hits, missing

    def grade_answer_with_llm(self, mission, answer):
        api_key = os.environ.get('OPENAI_API_KEY', '').strip()
        if not api_key:
            raise GraderUnavailable(API_KEY_MISSING_MESSAGE)

        answer = answer.strip()
        if not answer:
            return GradeResult(
                passed=False,
                hits=(),
                missing=tuple(fact.label for fact in mission.key_facts),
                response='Write a few facts first, then I can grade it.',
                grader='LLM grader')

        schema = {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'passed': {'type': 'boolean'},
                'hits': {'type': 'array', 'items': {'type': 'string'}},
                'missing': {'type': 'array', 'items': {'type': 'string'}},
                'response': {'type': 'string'},
            },
            'required': ['passed', 'hits', 'missing', 'response'],
        }
        key_facts = [
            {'label': fact.label, 'keywords': list(fact.keywords)}
            for fact in mission.key_facts
        ]
        prompt = {
            'mission_title': mission.title,
            'mission_prompt': mission.prompt,
            'required_hits': mission.required_hits,
            'key_facts': key_facts,
            'player_answer': answer,
        }
        body = {
            'model': os.environ.get('OPENAI_GRADER_MODEL', os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')),
            'input': [
                {
                    'role': 'system',
                    'content': (
                        'You are a concise in-game knowledge grader. Grade semantic coverage, '
                        'not exact wording. Count a key fact as hit if the player clearly explains '
                        'the idea, even with different words. Do not require every keyword. '
                        'Return supportive feedback in one short sentence. Do not reveal hidden '
                        'rubric details beyond the missing concepts.'
                    ),
                },
                {'role': 'user', 'content': json.dumps(prompt)},
            ],
            'text': {
                'format': {
                    'type': 'json_schema',
                    'name': 'mission_grade',
                    'strict': True,
                    'schema': schema,
                }
            },
        }
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }
        request = urllib.request.Request(
            OPENAI_RESPONSES_URL,
            data=json.dumps(body).encode('utf-8'),
            headers=headers,
            method='POST')

        try:
            with urllib.request.urlopen(request, timeout=LLM_GRADER_TIMEOUT) as response:
                payload = json.loads(response.read().decode('utf-8'))
            parsed = self.parse_llm_grade(payload)
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise GraderUnavailable(API_KEY_MISSING_MESSAGE) from error

        if not parsed:
            raise GraderUnavailable(API_KEY_MISSING_MESSAGE)

        hits = self.filter_fact_labels(parsed.get('hits', ()), mission)
        if not hits:
            hits = tuple(self.local_grade_answer(mission, answer)[0])
        missing = self.filter_fact_labels(parsed.get('missing', ()), mission)
        passed = bool(parsed.get('passed'))
        if passed:
            missing = ()
        elif not missing:
            all_labels = {fact.label for fact in mission.key_facts}
            missing = tuple(label for label in all_labels if label not in set(hits))
        return GradeResult(
            passed=passed,
            hits=tuple(hits),
            missing=tuple(missing),
            response=str(parsed.get('response', '')).strip()[:240] or 'Answer graded.',
            grader='LLM grader')

    def parse_llm_grade(self, payload):
        if isinstance(payload.get('output_text'), str):
            return json.loads(payload['output_text'])

        for item in payload.get('output', []):
            if item.get('type') != 'message':
                continue
            for content in item.get('content', []):
                if content.get('type') in ('output_text', 'text'):
                    return json.loads(content.get('text', '{}'))
        return None

    def filter_fact_labels(self, labels, mission):
        if not isinstance(labels, (list, tuple)):
            return ()
        allowed = {fact.label for fact in mission.key_facts}
        return tuple(label for label in labels if label in allowed)

    def reward_summary(self, mission):
        return f'Reward: {mission.reward_name} | Field: {mission.badge} | +{mission.xp} XP | +{mission.gold}g'

    def display_hud(self):
        self.poll_grading_result()
        self.poll_update_result()
        self.ensure_player_state()
        inventory = self.player.knowledge_inventory
        fields = ', '.join(
            self.skill_label(skill) for skill in self.player.knowledge_badges
        ) or 'no fields yet'
        rect = pygame.Rect(14, 12, 440, 112)
        pygame.draw.rect(self.display_surface, PANEL, rect, border_radius=5)
        pygame.draw.rect(self.display_surface, PANEL_DARK, rect, 2, border_radius=5)

        xp_surf = self.tiny_font.render(f'Knowledge XP {self.player.knowledge_xp}', False, INK)
        hp_color = WARNING if self.player.research_health <= 2 else INK
        hp_surf = self.tiny_font.render(
            f'Research HP {self.player.research_health}/{MAX_RESEARCH_HEALTH}', False, hp_color)
        read_today = date.today().isoformat() in self.player.paper_read_dates
        due_text = 'paper read today' if read_today else 'daily paper due'
        due_surf = self.tiny_font.render(due_text, False, SUCCESS if read_today else WARNING)
        badge_surf = self.tiny_font.render(fields, False, MUTED)
        self.display_surface.blit(xp_surf, (rect.left + 10, rect.top + 7))
        self.display_surface.blit(hp_surf, (rect.left + 154, rect.top + 7))
        self.display_surface.blit(due_surf, (rect.left + 302, rect.top + 7))
        self.display_surface.blit(badge_surf, (rect.left + 10, rect.top + 30))

        x = rect.left + 10
        y = rect.top + 56
        if inventory:
            for item, amount in inventory.items():
                slot_rect = pygame.Rect(x, y, 36, 36)
                self.draw_item_slot(slot_rect, item, amount, compact=True)
                x += 44
        else:
            empty_surf = self.tiny_font.render('chest empty', False, MUTED)
            self.display_surface.blit(empty_surf, (x, y + 8))

        help_surf = self.tiny_font.render('J journal | Enter near artifact or chest | daily paper protects HP', False, INK)
        help_rect = help_surf.get_rect(topleft=(14, rect.bottom + 6)).inflate(16, 8)
        pygame.draw.rect(self.display_surface, (238, 213, 164), help_rect, border_radius=5)
        self.display_surface.blit(help_surf, (help_rect.left + 8, help_rect.top + 4))

        if self.daily_notice:
            notice_surf = self.tiny_font.render(self.daily_notice, False, WARNING)
            notice_rect = notice_surf.get_rect(topleft=(14, help_rect.bottom + 6)).inflate(16, 8)
            pygame.draw.rect(self.display_surface, (248, 233, 196), notice_rect, border_radius=5)
            pygame.draw.rect(self.display_surface, PANEL_DARK, notice_rect, 2, border_radius=5)
            self.display_surface.blit(notice_surf, (notice_rect.left + 8, notice_rect.top + 4))

    def draw_item_slot(self, rect, item_id, amount=0, compact=False):
        slot = pygame.transform.scale(self.slot_surf, rect.size)
        self.display_surface.blit(slot, rect)

        icon = self.item_icons.get(item_id) or self.make_item_icon(item_id)
        if icon:
            inset = 3 if compact else 4
            icon_rect = rect.inflate(-inset * 2, -inset * 2)
            self.display_surface.blit(pygame.transform.scale(icon, icon_rect.size), icon_rect)

        if amount:
            amount_surf = self.tiny_font.render(str(amount), False, 'White')
            amount_bg = amount_surf.get_rect(bottomright=(rect.right - 2, rect.bottom - 1)).inflate(6, 2)
            pygame.draw.rect(self.display_surface, (57, 38, 29), amount_bg, border_radius=3)
            self.display_surface.blit(amount_surf, amount_surf.get_rect(center=amount_bg.center))

    def display(self):
        if self.welcome_active:
            self.draw_welcome_popup()
            return

        if self.update_popup_active:
            self.draw_update_popup()
            return

        if not self.active:
            return

        self.submit_button_rect = None

        shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 110))
        self.display_surface.blit(shade, (0, 0))

        panel = pygame.Rect(96, 72, SCREEN_WIDTH - 192, SCREEN_HEIGHT - 144)
        pygame.draw.rect(self.display_surface, PANEL_SHADOW, panel.move(6, 7), border_radius=8)
        pygame.draw.rect(self.display_surface, PANEL, panel, border_radius=8)
        pygame.draw.rect(self.display_surface, PANEL_DARK, panel, 4, border_radius=8)

        title_text = 'Artifact Chest' if self.collection_mode else 'Research Journal'
        title = self.font.render(title_text, False, INK)
        self.display_surface.blit(title, (panel.left + 24, panel.top + 16))

        left = pygame.Rect(panel.left + 24, panel.top + 64, 300, panel.height - 96)
        right = pygame.Rect(left.right + 28, left.top, panel.right - left.right - 52, left.height)
        if self.collection_mode:
            self.draw_collection_list(left)
            self.draw_collection_detail(right)
        else:
            self.draw_mission_list(left)
            self.draw_mission_detail(right)

    def draw_welcome_popup(self):
        self.submit_button_rect = None

        shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        shade.fill((31, 22, 15, 38))
        self.display_surface.blit(shade, (0, 0))

        slab = pygame.Rect(210, 76, SCREEN_WIDTH - 420, SCREEN_HEIGHT - 152)
        pygame.draw.rect(self.display_surface, (73, 45, 29), slab.move(7, 8), border_radius=8)
        pygame.draw.rect(self.display_surface, (191, 132, 72), slab, border_radius=8)
        pygame.draw.rect(self.display_surface, (91, 55, 35), slab, 4, border_radius=8)

        for plank_y in (slab.top + 68, slab.top + 142, slab.bottom - 94):
            pygame.draw.line(
                self.display_surface,
                (142, 91, 50),
                (slab.left + 16, plank_y),
                (slab.right - 16, plank_y),
                2)

        for knot in ((slab.left + 82, slab.top + 30), (slab.right - 136, slab.top + 96), (slab.left + 154, slab.bottom - 66)):
            pygame.draw.ellipse(self.display_surface, (146, 90, 48), (*knot, 48, 18))
            pygame.draw.ellipse(self.display_surface, (111, 67, 40), (knot[0] + 10, knot[1] + 4, 26, 8), 2)

        inset = slab.inflate(-58, -54)
        pygame.draw.rect(self.display_surface, (248, 233, 196), inset, border_radius=6)
        pygame.draw.rect(self.display_surface, (112, 70, 43), inset, 3, border_radius=6)

        title = self.font.render('Welcome to Scholardew Valley', False, INK)
        self.display_surface.blit(title, (inset.left + 22, inset.top + 18))

        y = inset.top + 70
        intro = (
            'Collect knowledge artifacts by reading papers and answering the mission questions. '
            'The grader needs an API key before it can score answers.'
        )
        y = self.draw_wrapped_clipped_top(
            intro,
            self.small_font,
            MUTED,
            inset.left + 22,
            y,
            inset.width - 44,
            y + 62)
        y += 14

        notes = (
            ('API key', 'Copy .env.example to .env, set OPENAI_API_KEY, then restart.'),
            ('Daily paper', 'A paper mission can appear each day; reading papers protects Research HP.'),
            ('Daily tasks', "Finish today's task list by midnight: +1 Strength and one Strawberry item."),
            ('Journal/chest', 'Press J for missions. Open the chest to review artifacts, rewards, and saved answers.'),
            ('Notebook', 'Press N to write durable notes or facts you want the game to remember.'),
        )

        row_left = inset.left + 20
        row_width = inset.width - 40
        row_height = 68
        for index, (heading, body) in enumerate(notes, start=1):
            row = pygame.Rect(row_left, y, row_width, row_height)
            color = (238, 219, 174) if index % 2 else (244, 226, 184)
            pygame.draw.rect(self.display_surface, color, row, border_radius=4)
            pygame.draw.rect(self.display_surface, (188, 142, 82), row, 1, border_radius=4)

            number_rect = pygame.Rect(row.left + 12, row.top + 12, 30, 30)
            pygame.draw.rect(self.display_surface, (207, 153, 74), number_rect, border_radius=4)
            pygame.draw.rect(self.display_surface, (112, 70, 43), number_rect, 2, border_radius=4)
            number_surf = self.tiny_font.render(str(index), False, INK)
            self.display_surface.blit(number_surf, number_surf.get_rect(center=number_rect.center))

            heading_surf = self.small_font.render(heading, False, ACCENT)
            self.display_surface.blit(heading_surf, (row.left + 54, row.top + 7))
            self.draw_wrapped_clipped_top(
                body,
                self.tiny_font,
                INK,
                row.left + 54,
                row.top + 32,
                row.width - 72,
                row.bottom - 6)
            y += row_height + 8

        self.welcome_button_rect = pygame.Rect(slab.right - 206, slab.bottom - 68, 166, 38)
        pygame.draw.rect(self.display_surface, (207, 153, 74), self.welcome_button_rect, border_radius=5)
        pygame.draw.rect(self.display_surface, (54, 35, 26), self.welcome_button_rect, 2, border_radius=5)
        button_label = self.small_font.render('Start', False, INK)
        self.display_surface.blit(button_label, button_label.get_rect(center=self.welcome_button_rect.center))

        hint = self.tiny_font.render('Enter / Space / Esc also closes this once.', False, (92, 76, 60))
        self.display_surface.blit(hint, (inset.left + 22, slab.bottom - 58))

    def draw_update_popup(self):
        self.submit_button_rect = None
        self.update_open_button_rect = None
        self.update_later_button_rect = None

        if not self.update_info:
            self.update_popup_active = False
            return

        shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        shade.fill((31, 22, 15, 46))
        self.display_surface.blit(shade, (0, 0))

        slab = pygame.Rect(260, 128, SCREEN_WIDTH - 520, SCREEN_HEIGHT - 256)
        pygame.draw.rect(self.display_surface, (73, 45, 29), slab.move(7, 8), border_radius=8)
        pygame.draw.rect(self.display_surface, (191, 132, 72), slab, border_radius=8)
        pygame.draw.rect(self.display_surface, (91, 55, 35), slab, 4, border_radius=8)

        inset = slab.inflate(-56, -52)
        pygame.draw.rect(self.display_surface, (248, 233, 196), inset, border_radius=6)
        pygame.draw.rect(self.display_surface, (112, 70, 43), inset, 3, border_radius=6)

        badge = pygame.Rect(inset.left + 22, inset.top + 24, 92, 34)
        pygame.draw.rect(self.display_surface, (207, 153, 74), badge, border_radius=5)
        pygame.draw.rect(self.display_surface, (112, 70, 43), badge, 2, border_radius=5)
        badge_text = self.tiny_font.render(f'v{self.update_info.version}', False, INK)
        self.display_surface.blit(badge_text, badge_text.get_rect(center=badge.center))

        title = self.font.render('Update Available', False, INK)
        self.display_surface.blit(title, (badge.right + 18, inset.top + 20))

        y = inset.top + 82
        subtitle = f'You are running Scholardew Valley v{APP_VERSION}.'
        y = self.draw_wrapped_clipped_top(
            subtitle,
            self.small_font,
            MUTED,
            inset.left + 24,
            y,
            inset.width - 48,
            y + 38)
        y += 10

        update_title = self.update_info.title
        if update_title:
            y = self.draw_wrapped_clipped_top(
                update_title,
                self.small_font,
                ACCENT,
                inset.left + 24,
                y,
                inset.width - 48,
                y + 44)
            y += 10

        y = self.draw_wrapped_clipped_top(
            self.update_info.message,
            self.tiny_font,
            INK,
            inset.left + 24,
            y,
            inset.width - 48,
            inset.bottom - 94)

        footer = self.tiny_font.render('Enter opens GitHub. Esc reminds you on the next version.', False, MUTED)
        self.display_surface.blit(footer, (inset.left + 24, inset.bottom - 84))

        self.update_later_button_rect = pygame.Rect(inset.right - 314, inset.bottom - 58, 112, 38)
        self.update_open_button_rect = pygame.Rect(inset.right - 184, inset.bottom - 58, 160, 38)

        pygame.draw.rect(self.display_surface, (232, 204, 151), self.update_later_button_rect, border_radius=5)
        pygame.draw.rect(self.display_surface, (112, 70, 43), self.update_later_button_rect, 2, border_radius=5)
        later_label = self.small_font.render('Later', False, INK)
        self.display_surface.blit(later_label, later_label.get_rect(center=self.update_later_button_rect.center))

        pygame.draw.rect(self.display_surface, (207, 153, 74), self.update_open_button_rect, border_radius=5)
        pygame.draw.rect(self.display_surface, (54, 35, 26), self.update_open_button_rect, 2, border_radius=5)
        open_label = self.small_font.render('Open GitHub', False, INK)
        self.display_surface.blit(open_label, open_label.get_rect(center=self.update_open_button_rect.center))

    def draw_collection_list(self, rect):
        pygame.draw.rect(self.display_surface, (232, 204, 151), rect, border_radius=6)
        pygame.draw.rect(self.display_surface, PANEL_DARK, rect, 2, border_radius=6)

        collected = self.collected_missions()
        header = self.small_font.render('Collected Artifacts', False, INK)
        self.display_surface.blit(header, (rect.left + 12, rect.top + 12))

        if not collected:
            empty = self.tiny_font.render('No artifacts stored yet.', False, MUTED)
            self.display_surface.blit(empty, (rect.left + 12, rect.top + 52))
            return

        gap = 8
        item_height = 68
        list_top = rect.top + 48
        visible_count = max(1, min(len(collected), (rect.bottom - list_top - 36) // (item_height + gap)))
        start = max(0, min(self.collection_index - visible_count // 2, len(collected) - visible_count))
        end = start + visible_count

        for visible_i, mission in enumerate(collected[start:end], start=start):
            item_rect = pygame.Rect(
                rect.left + 10,
                list_top + (visible_i - start) * (item_height + gap),
                rect.width - 20,
                item_height)
            selected = visible_i == self.collection_index
            color = (248, 232, 190) if selected else (222, 192, 137)
            pygame.draw.rect(self.display_surface, color, item_rect, border_radius=5)
            if selected:
                pygame.draw.rect(self.display_surface, ACCENT, item_rect, 3, border_radius=5)

            self.draw_item_slot(pygame.Rect(item_rect.left + 8, item_rect.top + 10, 46, 46), mission.reward_item)
            name = self.small_font.render(mission.reward_name, False, INK)
            field = self.tiny_font.render(mission.badge, False, SUCCESS)
            self.display_surface.blit(name, (item_rect.left + 64, item_rect.top + 8))
            self.display_surface.blit(field, (item_rect.left + 64, item_rect.top + 36))

        count_surf = self.tiny_font.render(f'{self.collection_index + 1}/{len(collected)}', False, MUTED)
        self.display_surface.blit(count_surf, (rect.right - count_surf.get_width() - 14, rect.bottom - 26))

    def draw_collection_detail(self, rect):
        pygame.draw.rect(self.display_surface, (248, 233, 196), rect, border_radius=6)
        pygame.draw.rect(self.display_surface, PANEL_DARK, rect, 2, border_radius=6)

        mission = self.selected_collection_mission()
        if not mission:
            y = rect.top + 24
            y = self.draw_wrapped('Collected artifacts will appear here after you answer their questions.', self.small_font, MUTED, rect.left + 18, y, rect.width - 36)
            footer = 'Enter near artifacts to collect | Esc close'
            footer_surf = self.tiny_font.render(footer, False, MUTED)
            self.display_surface.blit(footer_surf, (rect.left + 18, rect.bottom - 44))
            return

        record = self.player.artifact_records.get(mission.key, {})
        response = self.player.mission_responses.get(mission.key, {})
        collected_at = record.get('collected_at', 'Before chest log')
        footer_top = rect.bottom - 54
        grader_top = rect.bottom - 122
        content_bottom = grader_top - 14 if response.get('grader_response') else footer_top - 14
        y = rect.top + 18

        self.draw_item_slot(pygame.Rect(rect.left + 18, y + 2, 58, 58), mission.reward_item)
        title_x = rect.left + 92
        for line in self.wrap_text(mission.reward_name, self.font, rect.right - title_x - 18):
            surf = self.font.render(line, False, INK)
            self.display_surface.blit(surf, (title_x, y))
            y += surf.get_height() + 2
        meta = f'{mission.badge} | Collected: {collected_at} | +{mission.xp} XP | +{mission.gold}g'
        y = max(y + 6, rect.top + 82)
        y = self.draw_wrapped(meta, self.tiny_font, SUCCESS, rect.left + 18, y, rect.width - 36)
        y += 8

        desc_header = self.tiny_font.render('Artifact', False, INK)
        self.display_surface.blit(desc_header, (rect.left + 18, y))
        y += 24
        description = mission.artifact_description or mission.prompt
        description_bottom = min(y + 92, content_bottom - 92)
        if description_bottom > y + self.small_font.get_height():
            y = self.draw_wrapped_clipped_top(
                description,
                self.small_font,
                INK,
                rect.left + 18,
                y,
                rect.width - 36,
                description_bottom)
        y += 14

        if y < content_bottom - 44:
            pygame.draw.line(self.display_surface, (176, 132, 76), (rect.left + 18, y), (rect.right - 18, y), 1)
            y += 14
            answer_header = self.tiny_font.render('Your Answer', False, INK)
            self.display_surface.blit(answer_header, (rect.left + 18, y))
            y += 24

            answer_text = response.get('answer', '').strip()
            if answer_text:
                y = self.draw_wrapped_clipped(answer_text, self.tiny_font, INK, rect.left + 18, y, rect.width - 36, content_bottom)
            else:
                y = self.draw_wrapped_clipped_top('No saved answer for this artifact yet.', self.tiny_font, MUTED, rect.left + 18, y, rect.width - 36, content_bottom)

        grader_text = response.get('grader_response', '').strip()
        if grader_text:
            if grader_text.startswith('Grader:'):
                grader_text = grader_text.split(':', 1)[1].strip()
            feedback_top = grader_top
            pygame.draw.line(self.display_surface, (176, 132, 76), (rect.left + 18, feedback_top - 8), (rect.right - 18, feedback_top - 8), 1)
            grader_header = self.tiny_font.render('Grader', False, INK)
            self.display_surface.blit(grader_header, (rect.left + 18, feedback_top))
            self.draw_wrapped_clipped(
                grader_text,
                self.tiny_font,
                SUCCESS if response.get('passed') else WARNING,
                rect.left + 18,
                feedback_top + 24,
                rect.width - 36,
                footer_top - 4)

        footer = 'Up/Down artifacts | Esc close'
        footer_surf = self.tiny_font.render(footer, False, MUTED)
        self.display_surface.blit(footer_surf, (rect.left + 18, rect.bottom - 44))

    def draw_mission_list(self, rect):
        pygame.draw.rect(self.display_surface, (232, 204, 151), rect, border_radius=6)
        pygame.draw.rect(self.display_surface, PANEL_DARK, rect, 2, border_radius=6)

        chest_height = 156
        chest_rect = pygame.Rect(rect.left + 10, rect.bottom - chest_height - 12, rect.width - 20, chest_height)
        list_top = rect.top + 12
        available_height = chest_rect.top - list_top - 10
        gap = 6
        item_height = 54
        mission_order = self.ordered_mission_indices()
        current_pos = self.mission_order_position()
        visible_count = max(1, min(len(mission_order), available_height // (item_height + gap)))
        start = max(0, min(current_pos - visible_count // 2, len(mission_order) - visible_count))
        end = start + visible_count

        for visible_i, order_pos in enumerate(range(start, end)):
            mission_index = mission_order[order_pos]
            mission = self.missions[mission_index]
            item_rect = pygame.Rect(rect.left + 10, list_top + visible_i * (item_height + gap), rect.width - 20, item_height)
            selected = mission_index == self.index
            done = mission.key in self.player.completed_missions
            color = (248, 232, 190) if selected else (222, 192, 137)
            pygame.draw.rect(self.display_surface, color, item_rect, border_radius=5)
            if selected:
                pygame.draw.rect(self.display_surface, ACCENT, item_rect, 3, border_radius=5)

            status = 'DONE' if done else 'OPEN'
            status_color = SUCCESS if done else ACCENT
            title = self.small_font.render(mission.title, False, INK)
            status_surf = self.tiny_font.render(status, False, status_color)
            self.display_surface.blit(title, (item_rect.left + 12, item_rect.top + 5))
            self.display_surface.blit(status_surf, (item_rect.left + 12, item_rect.bottom - 24))

        if len(mission_order) > visible_count:
            range_surf = self.tiny_font.render(f'{current_pos + 1}/{len(mission_order)}', False, MUTED)
            self.display_surface.blit(range_surf, (rect.right - range_surf.get_width() - 18, chest_rect.top - 24))

        pygame.draw.rect(self.display_surface, (213, 177, 117), chest_rect, border_radius=5)
        pygame.draw.rect(self.display_surface, PANEL_DARK, chest_rect, 2, border_radius=5)
        label = self.small_font.render('Artifact Chest', False, INK)
        self.display_surface.blit(label, (chest_rect.left + 12, chest_rect.top + 10))

        inventory = list(self.chest_inventory().items())
        if not inventory:
            self.draw_wrapped_clipped_top(
                'Earn icons by answering missions or finishing daily tasks.',
                self.tiny_font,
                MUTED,
                chest_rect.left + 12,
                chest_rect.top + 48,
                chest_rect.width - 24,
                chest_rect.bottom - 10)
            return

        x = chest_rect.left + 12
        y = chest_rect.top + 48
        for item, amount in inventory[:6]:
            self.draw_item_slot(pygame.Rect(x, y, 48, 48), item, amount)
            x += 58
            if x + 48 > chest_rect.right - 10:
                x = chest_rect.left + 12
                y += 58

    def draw_mission_detail(self, rect):
        mission = self.missions[self.index]
        message, detail = self.current_feedback()
        pygame.draw.rect(self.display_surface, (248, 233, 196), rect, border_radius=6)
        pygame.draw.rect(self.display_surface, PANEL_DARK, rect, 2, border_radius=6)

        footer = 'Up/Down select | Enter/Cmd-S submit | E response | Esc close'
        footer_y = rect.bottom - 44
        status_rect = pygame.Rect(rect.left + 18, rect.bottom - 108, rect.width - 36, 54)
        content_bottom = status_rect.top - 12
        y = rect.top + 18
        for line in self.wrap_text(mission.title, self.font, rect.width - 36):
            surf = self.font.render(line, False, INK)
            self.display_surface.blit(surf, (rect.left + 18, y))
            y += surf.get_height() + 2

        source = self.tiny_font.render(mission.source, False, MUTED)
        self.display_surface.blit(source, (rect.left + 18, y + 4))
        y += 42

        y = self.draw_wrapped(mission.prompt, self.small_font, INK, rect.left + 18, y, rect.width - 36)
        y += 8

        compact_answer = self.answer_mode and bool(mission.questions)

        if mission.questions:
            y = self.draw_questions(mission.questions, rect.left + 18, y, rect.width - 36, compact_answer)
            y += 10

        if compact_answer:
            reward = self.tiny_font.render(
                self.reward_summary(mission),
                False,
                SUCCESS)
            self.display_surface.blit(reward, (rect.left + 18, y))
            y += 24
        else:
            reward_rect = pygame.Rect(rect.left + 18, y, rect.width - 36, 62)
            pygame.draw.rect(self.display_surface, (232, 217, 171), reward_rect, border_radius=5)
            self.draw_item_slot(pygame.Rect(reward_rect.left + 8, reward_rect.top + 7, 48, 48), mission.reward_item)
            self.draw_wrapped(
                self.reward_summary(mission),
                self.small_font,
                SUCCESS,
                reward_rect.left + 68,
                reward_rect.top + 13,
                reward_rect.width - 78)
            y = reward_rect.bottom + 16

        if self.answer_mode:
            label = self.small_font.render('Your answer:', False, INK)
            self.display_surface.blit(label, (rect.left + 18, y))
            y += 32

            input_height = 84 if compact_answer else 150
            input_height = max(48, min(input_height, content_bottom - y))
            if y + input_height > content_bottom:
                y = max(rect.top + 18, content_bottom - input_height)
            input_rect = pygame.Rect(rect.left + 18, y, rect.width - 36, input_height)
            pygame.draw.rect(self.display_surface, (255, 247, 221), input_rect, border_radius=5)
            pygame.draw.rect(self.display_surface, PANEL_DARK, input_rect, 2, border_radius=5)
            answer_text = self.answer if self.answer else 'type key facts here...'
            answer_color = INK if self.answer else MUTED
            self.draw_wrapped_clipped(
                answer_text,
                self.small_font,
                answer_color,
                input_rect.left + 12,
                input_rect.top + 10,
                input_rect.width - 24,
                input_rect.bottom - 8)
            y = input_rect.bottom + 10
        else:
            expanded = mission.key in self.expanded_responses
            if not expanded:
                facts = f'Grader wants about {mission.required_hits} of {len(mission.key_facts)} key facts.'
                y = self.draw_wrapped_clipped_top(facts, self.small_font, MUTED, rect.left + 18, y, rect.width - 36, content_bottom)
                y += 8
            if mission.key in self.player.mission_responses:
                response_label = 'Hide response' if mission.key in self.expanded_responses else 'Press E to review your response'
                response_surf = self.tiny_font.render(response_label, False, ACCENT)
                self.display_surface.blit(response_surf, (rect.left + 18, y))
                y += 26
                if mission.key in self.expanded_responses:
                    y = self.draw_response_panel(mission, rect.left + 18, y, rect.width - 36, content_bottom)
                    y += 10

        self.draw_status_bar(status_rect, message, detail, self.answer_mode)
        footer_surf = self.tiny_font.render(footer, False, MUTED)
        self.display_surface.blit(footer_surf, (rect.left + 18, footer_y))

    def draw_status_bar(self, rect, message, detail='', include_submit=False):
        pygame.draw.rect(self.display_surface, (232, 217, 171), rect, border_radius=5)
        pygame.draw.rect(self.display_surface, (176, 132, 76), rect, 2, border_radius=5)

        text_width = rect.width - 20
        if include_submit:
            self.submit_button_rect = pygame.Rect(rect.right - 164, rect.top + 9, 146, 36)
            text_width = self.submit_button_rect.left - rect.left - 16
            button_color = (196, 154, 85) if not self.grading else (164, 140, 100)
            pygame.draw.rect(self.display_surface, button_color, self.submit_button_rect, border_radius=5)
            pygame.draw.rect(self.display_surface, PANEL_DARK, self.submit_button_rect, 2, border_radius=5)
            label_text = 'Grading...' if self.grading else 'Submit'
            button_label = self.small_font.render(label_text, False, INK)
            self.display_surface.blit(button_label, button_label.get_rect(center=self.submit_button_rect.center))

        message_color = WARNING if self.is_warning_feedback(message, detail) else ACCENT
        y = rect.top + 7
        y = self.draw_wrapped_clipped_top(message, self.tiny_font, message_color, rect.left + 10, y, text_width, rect.top + 30)
        if detail:
            self.draw_wrapped_clipped_top(detail, self.nano_font, MUTED, rect.left + 10, y + 2, text_width, rect.bottom - 6)

    def is_warning_feedback(self, message, detail=''):
        text = f'{message} {detail}'.lower()
        return any(marker in text for marker in ('needs', 'try', 'unavailable', 'error', 'stronger'))

    def draw_response_panel(self, mission, x, y, width, bottom):
        response = self.player.mission_responses.get(mission.key)
        if not response:
            return y

        panel_height = min(230, max(116, bottom - y))
        if panel_height < 72:
            return y

        response_rect = pygame.Rect(x, y, width, panel_height)
        pygame.draw.rect(self.display_surface, (255, 247, 221), response_rect, border_radius=5)
        pygame.draw.rect(self.display_surface, PANEL_DARK, response_rect, 2, border_radius=5)

        header = self.tiny_font.render('Your Response', False, INK)
        self.display_surface.blit(header, (response_rect.left + 12, response_rect.top + 8))
        y = response_rect.top + 34
        feedback_top = response_rect.bottom - 70
        y = self.draw_wrapped_clipped(
            response.get('answer', ''),
            self.tiny_font,
            INK,
            response_rect.left + 12,
            y,
            response_rect.width - 24,
            feedback_top - 6)
        pygame.draw.line(
            self.display_surface,
            (176, 132, 76),
            (response_rect.left + 12, feedback_top - 6),
            (response_rect.right - 12, feedback_top - 6),
            1)
        grader_label = self.tiny_font.render('Grader', False, INK)
        self.display_surface.blit(grader_label, (response_rect.left + 12, feedback_top))
        grader_text = response.get('grader_response', '')
        if grader_text.startswith('Grader:'):
            grader_text = grader_text.split(':', 1)[1].strip()
        self.draw_wrapped_clipped(
            grader_text,
            self.tiny_font,
            SUCCESS if response.get('passed') else WARNING,
            response_rect.left + 12,
            feedback_top + 22,
            response_rect.width - 24,
            response_rect.bottom - 8)
        return response_rect.bottom

    def draw_questions(self, questions, x, y, width, compact=False):
        question_font = self.nano_font if compact else self.micro_font
        line_step = question_font.get_height() + (1 if compact else 2)
        question_gap = 2 if compact else 3
        header_height = 30
        bottom_padding = 10
        box_height = 134 if compact else 170
        box = pygame.Rect(x, y, width, box_height)
        self.question_panel_rect = box

        viewport = pygame.Rect(
            box.left + 10,
            box.top + header_height,
            box.width - 20,
            box.height - header_height - bottom_padding)
        col_gap = 18
        col_width = (viewport.width - col_gap) // 2
        columns = (
            (0, questions[:5]),
            (col_width + col_gap, questions[5:]),
        )
        wrapped_columns = []
        max_column_height = 0
        for col_x, col_questions in columns:
            wrapped_questions = []
            column_height = 0
            for index, question in enumerate(col_questions, start=1):
                prefix = 'C' if question.category == 'Conceptual' else 'M'
                line = f'{prefix}{index}. {question.text}'
                wrapped = self.wrap_text(line, question_font, col_width)
                wrapped_questions.append(wrapped)
                column_height += len(wrapped) * line_step + question_gap
            wrapped_columns.append((col_x, wrapped_questions))
            max_column_height = max(max_column_height, column_height)

        content_height = max(viewport.height, max_column_height)
        self.question_max_scroll = max(0, content_height - viewport.height)
        mission_key = self.missions[self.index].key
        scroll = max(0, min(self.question_scrolls.get(mission_key, 0), self.question_max_scroll))
        self.question_scrolls[mission_key] = scroll

        pygame.draw.rect(self.display_surface, (232, 217, 171), box, border_radius=5)
        pygame.draw.rect(self.display_surface, (176, 132, 76), box, 2, border_radius=5)
        header = self.tiny_font.render('Paper Questions', False, INK)
        self.display_surface.blit(header, (box.left + 10, box.top + 7))

        content_surface = pygame.Surface((viewport.width, content_height), pygame.SRCALPHA)
        for col_x, wrapped_questions in wrapped_columns:
            current_y = 0
            for wrapped_question in wrapped_questions:
                for wrapped in wrapped_question:
                    surf = question_font.render(wrapped, False, INK)
                    content_surface.blit(surf, (col_x, current_y))
                    current_y += line_step
                current_y += question_gap

        self.display_surface.blit(
            content_surface,
            viewport.topleft,
            pygame.Rect(0, scroll, viewport.width, viewport.height))

        if self.question_max_scroll:
            track = pygame.Rect(box.right - 12, viewport.top, 4, viewport.height)
            pygame.draw.rect(self.display_surface, (198, 158, 99), track, border_radius=2)
            thumb_height = max(18, int(track.height * viewport.height / content_height))
            thumb_range = max(1, track.height - thumb_height)
            thumb_y = track.top + int(thumb_range * (scroll / self.question_max_scroll))
            thumb = pygame.Rect(track.left, thumb_y, track.width, thumb_height)
            pygame.draw.rect(self.display_surface, PANEL_DARK, thumb, border_radius=2)

        return box.bottom

    def draw_wrapped_clipped(self, text, font, color, x, y, width, bottom):
        lines = self.wrap_text(text, font, width)
        line_height = font.get_height() + 4
        max_lines = max(1, (bottom - y) // line_height)
        clipped = len(lines) > max_lines
        visible_lines = lines[-max_lines:] if clipped else lines
        if clipped and visible_lines:
            visible_lines[0] = '... ' + visible_lines[0]

        for line in visible_lines:
            surf = font.render(line, False, color)
            self.display_surface.blit(surf, (x, y))
            y += line_height
        return y

    def draw_wrapped_clipped_top(self, text, font, color, x, y, width, bottom):
        lines = self.wrap_text(text, font, width)
        line_height = font.get_height() + 4
        max_lines = max(0, (bottom - y) // line_height)
        if max_lines <= 0:
            return y

        clipped = len(lines) > max_lines
        visible_lines = lines[:max_lines]
        if clipped and visible_lines:
            suffix = ' ...'
            last_line = visible_lines[-1]
            while last_line and font.size(last_line + suffix)[0] > width:
                last_line = last_line[:-1].rstrip()
            visible_lines[-1] = (last_line or visible_lines[-1]) + suffix

        for line in visible_lines:
            surf = font.render(line, False, color)
            self.display_surface.blit(surf, (x, y))
            y += line_height
        return y

    def draw_wrapped(self, text, font, color, x, y, width):
        for line in self.wrap_text(text, font, width):
            surf = font.render(line, False, color)
            self.display_surface.blit(surf, (x, y))
            y += surf.get_height() + 4
        return y

    def wrap_text(self, text, font, width):
        lines = []
        for paragraph in text.split('\n'):
            words = paragraph.split(' ')
            current = ''
            for word in words:
                candidate = word if not current else current + ' ' + word
                if font.size(candidate)[0] <= width:
                    current = candidate
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)
        return lines
