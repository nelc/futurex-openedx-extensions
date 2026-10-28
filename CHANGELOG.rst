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

* Raw counts (the default; ``fx_dashboard.legacy_filtered_counts`` off) now apply the same rule on every endpoint, so
  two endpoints that answer the same question give the same number. Version 0.13.14.

  * ``statistics/v1/total_counts/``: ``certificates_count`` and ``learning_hours`` include hidden courses on the
    cached path too, so ``certificates_count`` equals the sum of the course list's ``certificates_count``; with heavy
    queries on, learning hours no longer drop staff certificates.
  * ``statistics/v1/course_statuses/``: counts hidden courses, so the buckets add up to ``courses_count``.
  * ``learners/v1/learners/``: lists platform staff, superusers and course-team members (``is_active`` is kept), so
    ``count`` equals ``total_counts`` ``learners_count``; ``include_staff`` has no effect. Each learner's courses and
    certificates counts include hidden courses and the learner's course-team courses.
  * ``learners/v1/learner/<username>/``: same rule as the list. Course-team members are found without
    ``include_staff`` (it has no effect), and ``enrolled_courses_count`` / ``certificates_count`` equal the learner's
    row in the list.
  * ``courses/v1/courses/`` with heavy queries on: ``certificates_count`` no longer drops course-team certificates.
  * The legacy flag still restores every previous number. ``courses_count`` includes ``hidden_courses_count``; do not
    add them. Swagger text updated, including the learners list (it no longer claims enrolled users are listed).
* Bulk course progress feed: ``learner_search`` filters the rows to the learners whose full name, username, national
  ID or email contains the text (the same matching as ``learner_search`` elsewhere in ``/api/fx``), for example to look
  up one learner by national ID. The matched learners are resolved once, so the walk has no id windows (pages are
  full, usually one request) and ``count`` is their exact row total. More than 1000 matching learners answers 400.
  Version 0.13.13.
* Payments APIs for the Entity portal (version 0.13.12):

  * ``GET api/fx/payments/v1/tenants/``: payments status of the accessible tenants. ``active`` is true only when
    ``IS_ZEITLABS_PAYMENTS_ENABLED`` is on and the invoice identity and the card gateway settings are complete; it is
    computed from the tenant config on each call.
  * ``GET``/``PATCH api/fx/payments/v1/tenants/<tenant_id>/`` (system staff only): read or change the switch and the
    ``ZEITLABS_PAYMENTS_SETTINGS``, ``HYPERPAY_SETTINGS`` and ``HYPERPAY_MADA_SETTINGS`` values. ``ENTITY_ID`` and
    ``ACCESS_TOKEN`` are write-only (read back as ``is_set`` + last 4 characters); ``API_URL`` must be https on a
    HyperPay host; payments cannot be on with incomplete settings; each change logs the changed key names, never
    values.
  * ``GET api/fx/payments/v1/invoices/`` and ``invoices/<invoice_number>/``: paid invoices of the accessible courses
    as JSON (items, VAT, totals, buyer, seller identity, HyperPay payment id), filterable by ``course_ids`` and
    ``paid_at`` dates.
  * ``GET``/``PUT api/fx/payments/v1/courses/<course_id>/price/`` (system staff only): set the ``no-id-professional``
    mode and its catalogue item together with one sku and one whole-SAR price, and read a per-course readiness report.
  * ``api/fx/payments/v2/orders/`` returns ``transaction_id`` (the HyperPay payment id; null for manual payments).
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
