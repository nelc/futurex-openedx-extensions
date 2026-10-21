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
