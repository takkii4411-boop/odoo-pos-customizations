import json
import logging
from datetime import datetime

from odoo import http
from odoo.http import request

from rapidfuzz import process, fuzz

_logger = logging.getLogger(__name__)


class VoiceController(http.Controller):

    @http.route(
        "/voice/search_product",
        type="json",
        auth="user",
        csrf=False,
    )
    def search_product(self, text):
        products = request.env["product.product"].sudo().search([
            ("available_in_pos", "=", True)
        ])

        if not products:
            return {"success": False, "message": "No POS products found"}

        product_map = {}
        for product in products:
            name = product.name.lower().strip()
            display_name = (product.display_name or product.name).lower().strip()
            product_map[name] = {
                "id": product.id,
                "name": product.name,
                "price": product.lst_price,
            }
            if display_name != name:
                product_map[display_name] = product_map[name]

        query = text.lower().strip()

        # Strategy 1: token_sort_ratio (handles word order)
        best = process.extractOne(
            query,
            product_map.keys(),
            scorer=fuzz.token_sort_ratio,
        )

        # Strategy 2: if score low, try partial_ratio
        if not best or best[1] < 50:
            best2 = process.extractOne(
                query,
                product_map.keys(),
                scorer=fuzz.partial_ratio,
            )
            if best2 and best2[1] > (best[1] if best else 0):
                best = best2

        # Strategy 3: if still low, try token_set_ratio
        if not best or best[1] < 45:
            best3 = process.extractOne(
                query,
                product_map.keys(),
                scorer=fuzz.token_set_ratio,
            )
            if best3 and best3[1] > (best[1] if best else 0):
                best = best3

        if not best:
            return {"success": False, "message": "No product matched"}

        matched_name = best[0]
        score = best[1]

        _logger.info(
            'Product search: query="%s" matched="%s" score=%s',
            query, matched_name, score,
        )

        if score < 35:
            return {"success": False, "message": "Confidence too low"}

        result = dict(product_map[matched_name])
        result["score"] = score

        return {"success": True, "product": result}

    @http.route(
        "/voice/create_order",
        type="json",
        auth="user",
        csrf=False,
        methods=["POST"],
    )
    def create_order(self, **kwargs):
        data = json.loads(request.httprequest.data.decode())
        params = data.get("params", {})
        items = params.get("items", [])
        payment_method = params.get("payment_method", "cash")
        pos_config_id = params.get("pos_config_id", 1)

        order_lines = []
        total = 0.0
        for item in items:
            product = request.env["product.product"].sudo().browse(item["id"])
            if not product.exists():
                continue
            qty = item.get("qty", 1)
            subtotal = product.lst_price * qty
            line = [0, 0, {
                "product_id": product.id,
                "name": product.name,
                "price_unit": product.lst_price,
                "qty": qty,
                "price_subtotal": subtotal,
                "tax_ids": [[6, 0, []]],
            }]
            order_lines.append(line)
            total += subtotal

        payment_method_id = self._resolve_payment_method(payment_method)

        session = request.env["pos.session"].sudo().search([
            ("config_id", "=", pos_config_id),
            ("state", "=", "opened"),
        ], limit=1)
        session_id = session.id if session else False

        config = request.env["pos.config"].sudo().browse(pos_config_id)
        pricelist_id = config.pricelist_id.id if config and config.pricelist_id else False

        partner_id = params.get("partner_id", False)

        try:
            order_vals = {
                "name": datetime.now().strftime("Voice/%Y/%m/%d-%H:%M:%S"),
                "session_id": session_id,
                "config_id": pos_config_id,
                "lines": order_lines,
                "amount_total": total,
                "amount_paid": total,
                "amount_tax": 0.0,
                "amount_return": 0.0,
                "state": "paid",
                "payment_ids": [[0, 0, {
                    "amount": total,
                    "payment_method_id": payment_method_id,
                }]],
            }
            if pricelist_id:
                order_vals["pricelist_id"] = pricelist_id
            if partner_id:
                order_vals["partner_id"] = partner_id
            order = request.env["pos.order"].sudo().create(order_vals)
            return {"success": True, "order_id": order.id, "total": total}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _resolve_payment_method(self, method_name):
        mapping = {"cash": 1, "card": 2, "gcash": 3}
        method_id = mapping.get(method_name.lower(), 1)
        existing = request.env["pos.payment.method"].sudo().search([
            ("id", "=", method_id)
        ], limit=1)
        if existing:
            return method_id
        default = request.env["pos.payment.method"].sudo().search([], limit=1)
        return default.id if default else 1

    @http.route(
        "/voice/search_customer",
        type="json",
        auth="user",
        csrf=False,
    )
    def search_customer(self, text):
        query = text.strip().lower()
        if not query:
            return {"success": False, "message": "No query provided"}

        domain = [
            "|", "|",
            ("name", "=ilike", query + "%"),
            ("name", "=ilike", "%" + query + "%"),
            ("mobile", "=ilike", "%" + query + "%"),
        ]
        customers = request.env["res.partner"].sudo().search(domain, limit=20)

        if not customers:
            return {"success": False, "message": "No customer found"}

        results = []
        for c in customers:
            results.append({
                "id": c.id,
                "name": c.name,
                "phone": c.mobile or c.phone or "",
                "email": c.email or "",
            })
        return {"success": True, "customers": results}
