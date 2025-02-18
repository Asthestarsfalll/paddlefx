from __future__ import annotations

import dataclasses
import dis
import types

from typing import Callable

import paddle

from ._eval_frame import set_eval_frame
from .translator import InstructionTranslator, convert_instruction


@dataclasses.dataclass
class GuardedCode:
    code: types.CodeType
    # check_fn: GuardFn


class DynamoContext:
    def __init__(self, callback):
        self.callback = callback

    def __enter__(self):
        self.old_callback = set_eval_frame(self.callback)

    def __exit__(self, exc_type, exc_value, traceback):
        set_eval_frame(self.old_callback)

    def __call__(self, fn):
        def _fn(*args, **kwargs):
            old_callback = set_eval_frame(self.callback)

            result = fn(*args, **kwargs)

            set_eval_frame(old_callback)

            return result

        return _fn


def _compile(
    frame: types.FrameType,
    compiler_fn: Callable,
):
    code = frame.f_code
    instructions = list(map(convert_instruction, dis.get_instructions(code)))

    tracer = InstructionTranslator(instructions, frame, compiler_fn)
    tracer.run()

    # NOTE: just return the raw code from catched frame
    # TODO: support cache
    g = GuardedCode(code)
    return g


def has_tensor_in_frame(frame: types.FrameType) -> bool:
    # NOTE: skip paddle internal code
    if frame.f_code.co_filename.endswith('paddle/fluid/dygraph/math_op_patch.py'):
        return False
    if frame.f_code.co_name == 'in_dygraph_mode':
        return False

    # print(frame)
    # print(dis.disassemble(frame.f_code))

    for k, v in frame.f_locals.items():
        if isinstance(v, paddle.Tensor):
            return True

    return False


def convert_frame_assert(compiler_fn: Callable):
    def _convert_frame_assert(frame: types.FrameType):
        if not has_tensor_in_frame(frame):
            return None

        return _compile(frame, compiler_fn)

    return _convert_frame_assert


def optimize(backend=None):
    def convert_frame(compiler_fn):
        inner_convert = convert_frame_assert(compiler_fn)

        def _convert_frame(frame: types.FrameType):
            result = inner_convert(frame)
            return result

        return _convert_frame

    return DynamoContext(convert_frame(backend))
