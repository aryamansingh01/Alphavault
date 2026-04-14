try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler

try:
    from core.sectorscan import (
        screen_stocks, rank_by_metric, rank_with_composite, preset_screens,
    )
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.sectorscan import (
        screen_stocks, rank_by_metric, rank_with_composite, preset_screens,
    )


class handler(BaseHandler):
    def do_POST(self):
        try:
            body = self._body()
            preset_name = body.get("preset")
            custom_filters = body.get("filters", {})
            universe = body.get("universe")
            sort_by = body.get("sort_by")
            ascending = body.get("ascending", True)
            limit = body.get("limit", 50)
            include_composite = body.get("include_composite", False)

            # Resolve preset
            filters = {}
            presets = preset_screens()
            if preset_name and preset_name in presets:
                p = presets[preset_name]
                filters = dict(p["filters"])
                if not sort_by:
                    sort_by = p.get("sort_by", "composite_score")
                    ascending = p.get("ascending", True)

            # Merge custom filters (override preset)
            filters.update(custom_filters)

            # Screen
            results = screen_stocks(universe=universe, filters=filters if filters else None)

            # Composite scoring
            if include_composite or not sort_by:
                results = rank_with_composite(results)
                if not sort_by:
                    sort_by = "composite_score"
                    ascending = False

            # Sort
            if sort_by and sort_by != "composite_score":
                results = rank_by_metric(results, sort_by, ascending)

            # Limit
            total_passing = len(results)
            results = results[:limit]

            self._ok({
                "results": results,
                "total_screened": len(universe) if universe else 50,
                "total_passing": total_passing,
                "filters_applied": filters,
                "preset": preset_name,
                "available_presets": list(presets.keys()),
            })
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))
