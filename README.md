teslamate-comed
===============

ComEd hourly price cost calculation pushed to teslamate.

Using
-----

Environment variables:

* Point to teslamate database
    * `POSTGRES_HOST`
    * `POSTGRES_USER`
    * `POSTGRES_PASSWORD`
    * `POSTGRES_DB`
* `FIXED_COSTS` -- other fixed per-kWh costs to add in
* `TZ` -- `America/Chiago` by default
