Change Log
##########

..
   All enhancements and patches to futurex_openedx_extensions will be documented
   in this file.  It adheres to the structure of https://keepachangelog.com/ ,
   but in reStructuredText instead of Markdown (for ease of incorporation into
   Sphinx documentation and the PyPI description).

   This project adheres to Semantic Versioning (https://semver.org/).

.. There should always be an "Unreleased" section for changes pending release.

Unreleased
**********

* Bulk course progress feed: value filters ``progress_min`` / ``progress_max``, ``course_score_min`` /
  ``course_score_max`` (0 to 1; never-graded rows do not match a score filter), ``grade`` (comma-separated, exact) and
  ``passed`` (1 or 0; 0 = failed or never graded). They apply inside each page's id window, so pages stay as fast; with
  any of them ``count`` is null. A bad value answers 400. Version 0.13.11.
* Bulk course progress feed: ``count`` is now fast. It is the sum of per-course counts that ``sync_course_stats``
  keeps in ``CourseStat.progress_count`` (new column, migration ``0013_coursestat_progress_count``), instead of a
  live COUNT over the caller's whole scope, which took minutes for a platform-wide caller in 0.13.9. It is as fresh
  as the last sync, counts learners who unenrolled after starting (so it can be slightly above the rows walked), and
  is null with ``modified_since``. Run ``sync_course_stats --async`` once after the deploy and
  schedule it hourly. The response shape is unchanged. Version 0.13.10.
* The bulk course progress feed (``api/fx/learners/v1/learner_courses/`` without a username) now returns ``count``
  (the total rows of the walk) and ``page`` (1 for the first call) in every response. The total is counted once, on
  the call without a cursor, and carried in the cursor afterwards. Cursors issued before this change still work; their
  walks report ``count`` and ``page`` as null.
* Added the bulk course progress feed: ``api/fx/learners/v1/learner_courses/`` without a username returns one row per
  active enrollment with course completion above zero (national_id, user_id, email, course_id, date_joined,
  last_login, course_score, progress, certificate_available, certificate_date, grade, passed). Each request reads one
  window of 20,000 enrollment ids (up to ``page_size`` rows, 1000 by default and at most), so pages can be short or
  empty: follow ``next`` until it is null. No total count, optional ``modified_since`` filter. All values come from
  stored data in one query per page. The per-learner route with a username is unchanged.

0.1.0 – 2024-03-05
**********************************************

Added
=====

* First release on PyPI.
