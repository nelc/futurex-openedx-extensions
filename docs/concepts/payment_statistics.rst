Payment Statistics
==================

This document explains the mathematical logic behind the payment statistics provided by the dashboard API.

Overview
--------

The payment statistics module calculates key performance indicators (KPIs) for sales within a specified date range. The data is sourced from the ``zeitlabs_payments`` application, specifically the ``Cart`` and ``CartItem`` models.

Metrics
-------

The following metrics are calculated:

1. **Total Sales**
2. **Number of Orders**
3. **Average Order Value (AOV)**

Mathematical Definitions
------------------------

Let $C$ be the set of all carts such that:

*   The cart status is ``PAID``.
*   The cart's ``updated_at`` timestamp falls within the selected date range $[T_{start}, T_{end}]$.

Let $I$ be the set of all cart items belonging to carts in $C$. If a course filter is applied, $I$ is restricted to items corresponding to that course.

Total Sales
~~~~~~~~~~~

Total Sales is the sum of the final price of all relevant cart items.

.. math::

    \text{Total Sales} = \sum_{item \in I} \text{item.final\_price}

Number of Orders
~~~~~~~~~~~~~~~~

The Number of Orders is the count of unique carts associated with the relevant items.

.. math::

    \text{Number of Orders} = |\{ \text{item.cart} \mid item \in I \}|

Average Order Value (AOV)
~~~~~~~~~~~~~~~~~~~~~~~~~

The Average Order Value represents the average revenue generated per order.

.. math::

    \text{AOV} = \frac{\text{Total Sales}}{\text{Number of Orders}}

If $\text{Number of Orders} = 0$, then $\text{AOV} = 0$.

Daily Breakdown
---------------

The statistics are also aggregated on a daily basis to support visualization (e.g., graphs).

For each day $d$ in the range $[T_{start}, T_{end}]$:

1.  **Daily Sales ($S_d$)**: Sum of ``final_price`` for items where the cart was updated on day $d$.
2.  **Daily Orders ($O_d$)**: Count of unique carts updated on day $d$.
3.  **Daily Average ($A_d$)**:

.. math::

    A_d = \frac{S_d}{O_d}

Implementation Details
----------------------

The calculation is performed in ``futurex_openedx_extensions.dashboard.statistics.payments.get_payment_statistics``.

*   **Filters**:
    *   ``cart__status``: Must be ``'paid'``.
    *   ``cart__updated_at``: Must be within the provided ``from_date`` and ``to_date``.
    *   ``catalogue_item__item_ref_id``: (Optional) Filters by specific course ID.
    *   **Permissions**: The query is restricted to courses accessible to the requesting user.

*   **Aggregation**:
    *   Django's ``Sum`` and ``Count`` aggregation functions are used for efficient database-level calculation.
    *   ``TruncDay`` is used for grouping data by day.
