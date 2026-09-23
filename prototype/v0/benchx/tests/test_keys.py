import unittest

from benchx.worker import keys


class TokenEscaping(unittest.TestCase):
    def test_free_text_name_becomes_a_token(self):
        # Result tokens forbid whitespace; pyperf names are free text.
        self.assertEqual(keys.to_token("sort a sorted list"), "sort%20a%20sorted%20list")

    def test_percent_is_escaped_first(self):
        self.assertEqual(keys.to_token("50% of x"), "50%25%20of%20x")

    def test_structured_names_are_left_alone(self):
        self.assertEqual(keys.to_token("BM_Take/1024/2"), "BM_Take/1024/2")


class Keys(unittest.TestCase):
    def test_ingest_key_distinguishes_quantities_of_one_attempt(self):
        attempt = keys.new_attempt_key()
        self.assertNotEqual(
            keys.ingest_key(attempt, "wall-time"),
            keys.ingest_key(attempt, "cpu-time"),
        )

    def test_attempt_keys_are_namespaced_and_unique(self):
        first, second = keys.new_attempt_key(), keys.new_attempt_key()
        self.assertTrue(first.startswith("urn:uuid:"))
        self.assertNotEqual(first, second)

    def test_file_name_escapes_separators(self):
        name = keys.to_filename("urn:uuid:abc/wall-time")
        self.assertNotIn("/", name)
        self.assertNotIn(":", name)


if __name__ == "__main__":
    unittest.main()
