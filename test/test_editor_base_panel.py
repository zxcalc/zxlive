#     zxlive - An interactive tool for the ZX calculus
#     Copyright (C) 2023 - Aleks Kissinger
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#    http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import pytest

from zxlive.editor_base_panel import string_to_phase
from fractions import Fraction


def test_string_to_phase():
    # Test empty input clears the phase.
    assert string_to_phase('', None, 'fraction') == Fraction(0)

    # Test different ways of specifying integer multiples of pi.
    assert string_to_phase('3', None, 'fraction') == Fraction(3)
    assert string_to_phase('3pi', None, 'fraction') == Fraction(3)
    assert string_to_phase('3*pi', None, 'fraction') == Fraction(3)
    assert string_to_phase('pi*3', None, 'fraction') == Fraction(3)

    # Test different ways of specifying fractions.
    assert string_to_phase('pi/2', None, 'fraction') == Fraction(1,2)
    assert string_to_phase('-pi/2', None, 'fraction') == Fraction(-1,2)
    assert string_to_phase('5/2', None, 'fraction') == Fraction(5,2)
    assert string_to_phase('5pi/2', None, 'fraction') == Fraction(5,2)
    assert string_to_phase('5*pi/2', None, 'fraction') == Fraction(5,2)
    assert string_to_phase('pi*5/2', None, 'fraction') == Fraction(5,2)
    assert string_to_phase('5/2pi', None, 'fraction') == Fraction(5,2)
    assert string_to_phase('5/2*pi', None, 'fraction') == Fraction(5,2)
    assert string_to_phase('5/pi*2', None, 'fraction') == Fraction(5,2)

    # Test different ways of specifying floats.
    assert string_to_phase('5.5', None, 'fraction') == Fraction(11,2)
    assert string_to_phase('5.5pi', None, 'fraction') == Fraction(11,2)
    assert string_to_phase('25e-1', None, 'fraction') == Fraction(5,2)
    assert string_to_phase('5.5*pi', None, 'fraction') == Fraction(11,2)
    assert string_to_phase('pi*5.5', None, 'fraction') == Fraction(11,2)

    # TODO: test complex and polynomial input.

    # Test bad input.
    with pytest.raises(ValueError):
        string_to_phase('bad input', None, 'fraction')
