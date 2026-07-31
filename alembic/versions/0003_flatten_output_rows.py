"""0003 flatten multi-output indicator values into suffixed rows.

Replaces the JSON payload model for multi-output indicators with one row per
output component. Example: bbands_20_2 with {middle,upper,lower,bandwidth}
becomes four rows with codes:
- bbands_20_2_middle
- bbands_20_2_upper
- bbands_20_2_lower
- bbands_20_2_bandwidth

After flattening existing data, drops indicators.indicator_values.values_json.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_flatten_output_rows"
down_revision: Union[str, None] = "0002_current_values_only"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Expand multi-output rows into one row per named output.
    op.execute(
        """
        INSERT INTO indicators.indicator_values (
            symbol_id,
            ticker,
            bar_date,
            indicator_code,
            indicator_version,
            adjustment_type,
            value,
            indicator_run_id,
            created_at,
            updated_at
        )
        SELECT
            iv.symbol_id,
            iv.ticker,
            iv.bar_date,
            iv.indicator_code || '_' || kv.key AS indicator_code,
            iv.indicator_version,
            iv.adjustment_type,
            NULLIF(kv.value, 'null')::numeric(20,8) AS value,
            iv.indicator_run_id,
            iv.created_at,
            iv.updated_at
        FROM indicators.indicator_values iv
        CROSS JOIN LATERAL jsonb_each_text(COALESCE(iv.values_json::jsonb, '{}'::jsonb)) kv
        WHERE iv.values_json IS NOT NULL
        ON CONFLICT (symbol_id, indicator_code, indicator_version, adjustment_type)
        DO UPDATE SET
            ticker = EXCLUDED.ticker,
            bar_date = EXCLUDED.bar_date,
            value = EXCLUDED.value,
            indicator_run_id = EXCLUDED.indicator_run_id,
            updated_at = now()
        """
    )

    # Remove legacy multi-output rows after expansion.
    op.execute(
        """
        DELETE FROM indicators.indicator_values
        WHERE values_json IS NOT NULL
        """
    )

    op.drop_column("indicator_values", "values_json", schema="indicators")


def downgrade() -> None:
    op.add_column(
        "indicator_values",
        sa.Column("values_json", sa.JSON(), nullable=True),
        schema="indicators",
    )

    # Rebuild JSON rows for multi-output indicators based on indicator_definitions.
    op.execute(
        """
        INSERT INTO indicators.indicator_values (
            symbol_id,
            ticker,
            bar_date,
            indicator_code,
            indicator_version,
            adjustment_type,
            value,
            values_json,
            indicator_run_id,
            created_at,
            updated_at
        )
        SELECT
            x.symbol_id,
            x.ticker,
            x.bar_date,
            x.base_code,
            x.indicator_version,
            x.adjustment_type,
            NULL::numeric(20,8) AS value,
            jsonb_object_agg(x.output_name, x.output_value) AS values_json,
            max(x.indicator_run_id) AS indicator_run_id,
            min(x.created_at) AS created_at,
            max(x.updated_at) AS updated_at
        FROM (
            SELECT
                iv.symbol_id,
                iv.ticker,
                iv.bar_date,
                d.code AS base_code,
                iv.indicator_version,
                iv.adjustment_type,
                o.output_name,
                to_jsonb(iv.value) AS output_value,
                iv.indicator_run_id,
                iv.created_at,
                iv.updated_at
            FROM indicators.indicator_values iv
            JOIN indicators.indicator_definitions d
              ON d.version = iv.indicator_version
            JOIN LATERAL jsonb_array_elements_text(COALESCE(d.outputs::jsonb, '[]'::jsonb)) o(output_name)
              ON iv.indicator_code = d.code || '_' || o.output_name
        ) AS x
        GROUP BY
            x.symbol_id,
            x.ticker,
            x.bar_date,
            x.base_code,
            x.indicator_version,
            x.adjustment_type
        ON CONFLICT (symbol_id, indicator_code, indicator_version, adjustment_type)
        DO UPDATE SET
            ticker = EXCLUDED.ticker,
            bar_date = EXCLUDED.bar_date,
            value = EXCLUDED.value,
            values_json = EXCLUDED.values_json,
            indicator_run_id = EXCLUDED.indicator_run_id,
            updated_at = now()
        """
    )

    # Remove flattened component rows that were collapsed back into JSON rows.
    op.execute(
        """
        DELETE FROM indicators.indicator_values iv
        USING indicators.indicator_definitions d,
              LATERAL jsonb_array_elements_text(COALESCE(d.outputs::jsonb, '[]'::jsonb)) o(output_name)
        WHERE d.version = iv.indicator_version
          AND iv.indicator_code = d.code || '_' || o.output_name
        """
    )
