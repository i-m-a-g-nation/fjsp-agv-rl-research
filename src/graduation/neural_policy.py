"""Small NumPy masked MLP/REINFORCE baseline, independent of domain rules."""
from dataclasses import dataclass
import math

import numpy as np

from src.graduation.state_encoding import TypedStateEncoding, decode_construction_observation

FEATURE_COUNT = 372
ACTION_COUNT = 100
PARAMETER_KEYS = ('w1', 'b1', 'w2', 'b2')


def policy_features(encoded: TypedStateEncoding) -> tuple[float, ...]:
    decode_construction_observation(encoded)  # Validate source format; no environment mutation.
    if encoded.scale > 2**50:
        raise ValueError('Policy scale exceeds the declared R1 numeric range')
    return (tuple(value for row in encoded.rows for value in row)
        + tuple(float(encoded.mode == mode) for mode in ('fixed', 'joint'))
        + tuple(float(encoded.status == status) for status in ('ACTIVE', 'TERMINATED', 'TRUNCATED', 'FAILED'))
        + (encoded.steps / 28, math.log1p(encoded.scale) / math.log1p(2**50)))


def _mask(mask):
    if (type(mask) is not tuple or len(mask) != ACTION_COUNT
            or any(type(value) is not bool for value in mask) or not any(mask)):
        raise ValueError('Policy needs a nonempty exact100 boolean action mask')


def _features(features):
    if (type(features) is not tuple or len(features) != FEATURE_COUNT
            or any(type(value) is not float or not math.isfinite(value) for value in features)):
        raise ValueError('Policy features must be372 finite built-in floats')


def masked_probabilities(logits: np.ndarray, mask: tuple[bool, ...]) -> np.ndarray:
    _mask(mask)
    if (type(logits) is not np.ndarray or logits.dtype != np.float64 or logits.shape != (ACTION_COUNT,)
            or not np.isfinite(logits).all()):
        raise ValueError('Expected100 finite float64 policy logits')
    legal = np.asarray(mask, dtype=bool)
    probabilities = np.zeros(ACTION_COUNT, dtype=np.float64)
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise', under='ignore'):
            weights = np.exp(logits[legal] - np.max(logits[legal]))
            probabilities[legal] = weights / weights.sum()
    except FloatingPointError as exc:
        raise ValueError('Masked distribution is numerically invalid') from exc
    if not np.isfinite(probabilities).all():
        raise ValueError('Masked probabilities must remain finite')
    return probabilities


@dataclass(frozen=True)
class PolicySample:
    features: tuple[float, ...]
    action_mask: tuple[bool, ...]
    action: int
    return_value: float

    def __post_init__(self):
        _validate_sample(self)


def _validate_sample(sample):
    if type(sample) is not PolicySample:
        raise ValueError('Expected a PolicySample')
    _features(sample.features)
    _mask(sample.action_mask)
    if (type(sample.action) is not int or not 0 <= sample.action < ACTION_COUNT
            or not sample.action_mask[sample.action]
            or type(sample.return_value) is not float or not math.isfinite(sample.return_value)):
        raise ValueError('Sample action/return is invalid')


def _validate_parameters(state):
    if type(state) is not dict or set(state) != set(PARAMETER_KEYS):
        raise ValueError('Checkpoint must contain exactlyw1,b1,w2,b2')
    if any(type(value) is not np.ndarray or value.dtype != np.float64 or not np.isfinite(value).all()
           for value in state.values()):
        raise ValueError('Checkpoint arrays must be finite float64')
    w1 = state['w1']
    if w1.ndim != 2 or w1.shape[0] != FEATURE_COUNT or not 1 <= w1.shape[1] <= 16:
        raise ValueError('Invalid policy input/hidden dimensions')
    hidden = w1.shape[1]
    if state['b1'].shape != (hidden,) or state['w2'].shape != (hidden, ACTION_COUNT) or state['b2'].shape != (ACTION_COUNT,):
        raise ValueError('Inconsistent policy parameter shapes')
    return hidden


class MaskedMLP:
    """Two learned affine layers with tanh; only masked stochastic/greedy actions."""

    def __init__(self, *, seed: int, hidden_size: int = 16):
        if (type(seed) is not int or not 0 <= seed <= 2**32-1
                or type(hidden_size) is not int or not 1 <= hidden_size <= 16):
            raise ValueError('Expected uint32 seed and hidden size1..16')
        rng = np.random.Generator(np.random.PCG64(seed))
        self._parameters = {
            'w1': rng.normal(0., 1/math.sqrt(FEATURE_COUNT), (FEATURE_COUNT, hidden_size)),
            'b1': np.zeros(hidden_size, dtype=np.float64),
            'w2': rng.normal(0., 1/math.sqrt(hidden_size), (hidden_size, ACTION_COUNT)),
            'b2': np.zeros(ACTION_COUNT, dtype=np.float64)}

    @property
    def hidden_size(self):
        return _validate_parameters(self._parameters)

    def state_dict(self) -> dict[str, np.ndarray]:
        _validate_parameters(self._parameters)
        return {name: value.copy() for name, value in self._parameters.items()}

    @classmethod
    def from_state(cls, state):
        hidden = _validate_parameters(state)
        actor = cls(seed=0, hidden_size=hidden)
        actor._parameters = {name: value.copy() for name, value in state.items()}
        return actor

    def _forward(self, features):
        _features(features)
        _validate_parameters(self._parameters)
        weights = self._parameters
        x = np.asarray(features, dtype=np.float64)
        try:
            with np.errstate(over='raise', invalid='raise'):
                hidden = np.tanh(x @ weights['w1'] + weights['b1'])
                logits = hidden @ weights['w2'] + weights['b2']
        except FloatingPointError as exc:
            raise ValueError('Policy forward pass is numerically invalid') from exc
        if not np.isfinite(hidden).all() or not np.isfinite(logits).all():
            raise ValueError('Policy forward pass must remain finite')
        return x, hidden, logits

    def probabilities(self, encoded: TypedStateEncoding) -> tuple[float, ...]:
        features = policy_features(encoded)
        if encoded.status != 'ACTIVE':
            raise ValueError('Only an ACTIVE observation can request a policy action')
        _, _, logits = self._forward(features)
        return tuple(masked_probabilities(logits, encoded.action_mask).tolist())

    def select_action(self, encoded: TypedStateEncoding, *, rng: np.random.Generator,
                      deterministic: bool = False) -> int:
        if not isinstance(rng, np.random.Generator) or type(deterministic) is not bool:
            raise ValueError('Use a caller-owned Generator and explicit boolean selection mode')
        probabilities = self.probabilities(encoded)
        return int(np.argmax(probabilities) if deterministic else rng.choice(ACTION_COUNT, p=probabilities))

    def log_probability_gradient(self, sample: PolicySample):
        _validate_sample(sample)
        x, hidden, logits = self._forward(sample.features)
        probabilities = masked_probabilities(logits, sample.action_mask)
        legal_logits = logits[np.asarray(sample.action_mask, dtype=bool)]
        maximum = float(np.max(legal_logits))
        log_probability = float(logits[sample.action] - maximum - np.log(np.exp(legal_logits-maximum).sum()))
        dz = -probabilities
        dz[sample.action] += 1.
        dh = (self._parameters['w2'] @ dz) * (1. - hidden*hidden)
        gradients = {'w1': np.outer(x, dh), 'b1': dh,
                     'w2': np.outer(hidden, dz), 'b2': dz}
        if not math.isfinite(log_probability) or any(not np.isfinite(g).all() for g in gradients.values()):
            raise ValueError('Policy gradient must remain finite')
        return log_probability, gradients

    def reinforce_update(self, samples: tuple[PolicySample, ...], *, learning_rate: float = .01,
                         max_grad_norm: float = 1.) -> dict:
        if (type(samples) is not tuple or not 1 <= len(samples) <= 28
                or type(learning_rate) is not float or not math.isfinite(learning_rate) or not 0 < learning_rate <= 1
                or type(max_grad_norm) is not float or not math.isfinite(max_grad_norm) or not 0 < max_grad_norm <= 10):
            raise ValueError('Invalid bounded REINFORCE update configuration')
        for sample in samples:
            _validate_sample(sample)
        total = {name: np.zeros_like(value) for name, value in self._parameters.items()}
        loss = 0.
        try:
            with np.errstate(over='raise', invalid='raise'):
                for sample in samples:
                    logp, gradient = self.log_probability_gradient(sample)
                    loss -= sample.return_value * logp / len(samples)
                    for name in total:
                        total[name] += (sample.return_value / len(samples)) * gradient[name]
                norm = math.sqrt(sum(float(np.sum(g*g)) for g in total.values()))
                if not math.isfinite(norm) or not math.isfinite(loss):
                    raise ValueError('Update loss/norm must remain finite')
                factor = min(1., max_grad_norm / norm) if norm else 1.
                candidate = {name: value + learning_rate*factor*total[name] for name, value in self._parameters.items()}
        except FloatingPointError as exc:
            raise ValueError('Policy update is numerically invalid') from exc
        _validate_parameters(candidate)
        changed = any(not np.array_equal(value, candidate[name]) for name, value in self._parameters.items())
        self._parameters = candidate
        return {'loss': float(loss), 'gradient_norm': float(norm), 'applied_gradient_norm': float(norm*factor),
                'changed': bool(changed), 'samples': len(samples)}
