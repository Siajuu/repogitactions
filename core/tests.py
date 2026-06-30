from django.test import TestCase

from core.tasks import add, multiply, reverse_text


class SanityCheckTests(TestCase):
    def test_basic_math(self):
        self.assertEqual(1 + 1, 2)

    def test_string_concatenation(self):
        self.assertEqual("Hello, " + "World!", "Hello, World!")


class CeleryTaskTests(TestCase):
    def test_add_task(self):
        result = add.delay(2, 3)
        self.assertEqual(result.get(timeout=10), 5)

    def test_multiply_task(self):
        result = multiply.delay(4, 5)
        self.assertEqual(result.get(timeout=10), 20)

    def test_reverse_text_task(self):
        result = reverse_text.delay("hello")
        self.assertEqual(result.get(timeout=10), "olleh")
