from django.test import TestCase


class SanityCheckTests(TestCase):
    def test_basic_math(self):
        self.assertEqual(1 + 1, 2)

    def test_string_concatenation(self):
        self.assertEqual("Hello, " + "World!", "Hello, World!")
