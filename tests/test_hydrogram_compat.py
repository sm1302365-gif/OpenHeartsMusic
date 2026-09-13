import unittest

import hydrogram.errors as hydrogram_errors

from OpenHeartsMusic.compat import install_hydrogram_error_aliases


class HydrogramCompatibilityTests(unittest.TestCase):
    def test_groupcall_error_names_are_available_to_rpc_mapper(self):
        install_hydrogram_error_aliases()

        self.assertIs(hydrogram_errors.GroupcallInvalid, hydrogram_errors.GroupCallInvalid)
        self.assertTrue(issubclass(hydrogram_errors.GroupcallForbidden, hydrogram_errors.BadRequest))
        self.assertEqual(hydrogram_errors.GroupcallForbidden.ID, "GROUPCALL_FORBIDDEN")


if __name__ == "__main__":
    unittest.main()
