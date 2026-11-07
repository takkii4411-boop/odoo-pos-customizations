# Copyright 2015 ABF OSIELL <https://osiell.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import UserError
import base64
import io
import pytz
from pytz import timezone, UTC


class AuditlogLog(models.Model):
    _name = "auditlog.log"
    _description = "Auditlog - Log"
    _order = "create_date desc"

    name = fields.Char("Resource Name", size=64)
    model_id = fields.Many2one(
        "ir.model", string="Model", index=True, ondelete="set null"
    )
    model_name = fields.Char(readonly=True)
    model_model = fields.Char(string="Technical Model Name", readonly=True)
    res_id = fields.Integer("Resource ID")
    user_id = fields.Many2one("res.users", string="User")
    method = fields.Char(size=64)
    line_ids = fields.One2many("auditlog.log.line", "log_id", string="Fields updated")
    http_session_id = fields.Many2one(
        "auditlog.http.session", string="Session", index=True
    )
    http_request_id = fields.Many2one(
        "auditlog.http.request", string="HTTP Request", index=True
    )
    log_type = fields.Selection(
        [("full", "Full log"), ("fast", "Fast log")], string="Type"
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Insert model_name and model_model field values upon creation."""
        for vals in vals_list:
            if not vals.get("model_id"):
                raise UserError(_("No model defined to create log."))
            model = self.env["ir.model"].sudo().browse(vals["model_id"])
            vals.update({"model_name": model.name, "model_model": model.model})
        return super().create(vals_list)

    def action_export_sales_price_change_report(self, date_from=None, date_to=None):
        """
        Sales Price Change Report
        Format: 03-11-2026 10:06:12,Product,SAMPLE Item A, Sales Price updated from 100 to 120
        """
        from datetime import datetime

        output = io.StringIO()

        domain = [
            ('model_model', '=', 'product.template'),
            ('method', '=', 'write'),
        ]
        if date_from:
            domain.append(('create_date', '>=', date_from))
        if date_to:
            domain.append(('create_date', '<=', date_to))

        logs = self.env['auditlog.log'].search(domain, order='create_date asc')

        lines_written = 0
        for log in logs:
            for line in log.line_ids:
                if line.field_name == 'list_price':

                    log_date = log.create_date
                    if log_date:
                        try:
                            import tzlocal
                            tz = tzlocal.get_localzone()
                        except ImportError:
                            tz_name = self.env.user.tz or 'UTC'
                            tz = pytz.timezone(tz_name)

                        local_date = log_date.replace(tzinfo=pytz.UTC).astimezone(tz)
                        formatted_date = local_date.strftime('%m-%d-%Y %H:%M:%S')
                    else:
                        formatted_date = ''

                    old_price = line.old_value_text or '0'
                    new_price = line.new_value_text or '0'
                    product_name = log.name or 'Unknown'

                    row = "%s,Product,%s, Sales Price updated from %s to %s\n" % (
                        formatted_date,
                        product_name,
                        old_price,
                        new_price,
                    )
                    output.write(row)
                    lines_written += 1

        if lines_written == 0:
            output.write("No sales price changes found.\n")

        tz_name = self.env.user.tz or 'UTC'
        user_tz = pytz.timezone(tz_name)

        date_from_str = date_from.replace(tzinfo=pytz.UTC).astimezone(user_tz).strftime('%m-%d-%Y') if date_from else ''
        date_to_str = date_to.replace(tzinfo=pytz.UTC).astimezone(user_tz).strftime('%m-%d-%Y') if date_to else ''
        file_name = "Sales Price Change Report.%s to %s.txt" % (date_from_str, date_to_str)
        csv_data = base64.b64encode(output.getvalue().encode('utf-8'))

        attachment = self.env['ir.attachment'].create({
            'name': file_name,
            'datas': csv_data,
            'mimetype': 'text/plain',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }

    def action_export_employee_add_remove_report(self, date_from=None, date_to=None):
        """
        Employee Add Remove Report
        Format: 03-11-2026 15:23:12,Employee,Cashier 2,Added
        """
        output = io.StringIO()

        domain = [
            ('model_model', '=', 'hr.employee'),
            ('method', 'in', ['create', 'unlink', 'write']),
        ]
        if date_from:
            domain.append(('create_date', '>=', date_from))
        if date_to:
            domain.append(('create_date', '<=', date_to))

        logs = self.env['auditlog.log'].search(domain, order='create_date asc')

        lines_written = 0
        for log in logs:
            log_date = log.create_date
            if log_date:
                try:
                    import tzlocal
                    tz = tzlocal.get_localzone()
                except ImportError:
                    tz_name = self.env.user.tz or 'UTC'
                    tz = pytz.timezone(tz_name)

                local_date = log_date.replace(tzinfo=pytz.UTC).astimezone(tz)
                formatted_date = local_date.strftime('%m-%d-%Y %H:%M:%S')
            else:
                formatted_date = ''

            employee_name = log.name or 'Unknown'
            if log.method == 'create':
                action = 'Added'
            elif log.method == 'unlink':
                action = 'Removed'
            else:
                active_line = log.line_ids.filtered(lambda l: l.field_name == 'active')
                if not active_line:
                    continue
                new_val = (active_line[0].new_value_text or '').strip()
                old_val = (active_line[0].old_value_text or '').strip()
                if new_val == 'True':
                    action = 'Added'
                elif new_val == 'False' or (old_val == 'True' and new_val == ''):
                    action = 'Removed'
                else:
                    continue

            row = "%s,Employee,%s,%s\n" % (
                formatted_date,
                employee_name,
                action,
            )
            output.write(row)
            lines_written += 1

        if lines_written == 0:
            output.write("No employee add/remove records found.\n")

        tz_name = self.env.user.tz or 'UTC'
        user_tz = pytz.timezone(tz_name)

        date_from_str = date_from.replace(tzinfo=pytz.UTC).astimezone(user_tz).strftime('%m-%d-%Y') if date_from else ''
        date_to_str = date_to.replace(tzinfo=pytz.UTC).astimezone(user_tz).strftime('%m-%d-%Y') if date_to else ''
        file_name = "Employee Add Remove Report.%s to %s.txt" % (date_from_str, date_to_str)
        csv_data = base64.b64encode(output.getvalue().encode('utf-8'))

        attachment = self.env['ir.attachment'].create({
            'name': file_name,
            'datas': csv_data,
            'mimetype': 'text/plain',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }

    def action_export_product_add_remove_report(self, date_from=None, date_to=None):
        """
        Product Add Remove Report
        Format: 03-11-2026 15:23:12,Product,SAMPLE Item A,Added
        """
        output = io.StringIO()

        domain = [
            ('model_model', '=', 'product.template'),
            ('method', 'in', ['create', 'unlink', 'write']),
        ]
        if date_from:
            domain.append(('create_date', '>=', date_from))
        if date_to:
            domain.append(('create_date', '<=', date_to))

        logs = self.env['auditlog.log'].search(domain, order='create_date asc')

        lines_written = 0
        for log in logs:
            log_date = log.create_date
            if log_date:
                try:
                    import tzlocal
                    tz = tzlocal.get_localzone()
                except ImportError:
                    tz_name = self.env.user.tz or 'UTC'
                    tz = pytz.timezone(tz_name)

                local_date = log_date.replace(tzinfo=pytz.UTC).astimezone(tz)
                formatted_date = local_date.strftime('%m-%d-%Y %H:%M:%S')
            else:
                formatted_date = ''

            product_name = log.name or 'Unknown'
            if log.method == 'create':
                action = 'Added'
            elif log.method == 'unlink':
                action = 'Removed'
            else:
                # write method — check active field
                active_line = log.line_ids.filtered(lambda l: l.field_name == 'active')
                if not active_line:
                    continue
                new_val = (active_line[0].new_value_text or '').strip()
                old_val = (active_line[0].old_value_text or '').strip()
                if new_val == 'True':
                    action = 'Added'
                elif new_val == 'False' or (old_val == 'True' and new_val == ''):
                    action = 'Removed'
                else:
                    continue

            row = "%s,Product,%s,%s\n" % (
                formatted_date,
                product_name,
                action,
            )
            output.write(row)
            lines_written += 1

        if lines_written == 0:
            output.write("No product add/remove records found.\n")

        tz_name = self.env.user.tz or 'UTC'
        user_tz = pytz.timezone(tz_name)

        date_from_str = date_from.replace(tzinfo=pytz.UTC).astimezone(user_tz).strftime('%m-%d-%Y') if date_from else ''
        date_to_str = date_to.replace(tzinfo=pytz.UTC).astimezone(user_tz).strftime('%m-%d-%Y') if date_to else ''
        file_name = "Product Add Remove Report.%s to %s.txt" % (date_from_str, date_to_str)
        csv_data = base64.b64encode(output.getvalue().encode('utf-8'))

        attachment = self.env['ir.attachment'].create({
            'name': file_name,
            'datas': csv_data,
            'mimetype': 'text/plain',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }

    def write(self, vals):
        """Update model_name and model_model field values to reflect model_id
        changes."""
        if "model_id" in vals:
            if not vals["model_id"]:
                raise UserError(_("The field 'model_id' cannot be empty."))
            model = self.env["ir.model"].sudo().browse(vals["model_id"])
            vals.update({"model_name": model.name, "model_model": model.model})
        return super().write(vals)


class AuditlogLogLine(models.Model):
    _name = "auditlog.log.line"
    _description = "Auditlog - Log details (fields updated)"

    field_id = fields.Many2one(
        "ir.model.fields", ondelete="set null", string="Field", index=True
    )
    log_id = fields.Many2one(
        "auditlog.log", string="Log", ondelete="cascade", index=True
    )
    old_value = fields.Text()
    new_value = fields.Text()
    old_value_text = fields.Text("Old value Text")
    new_value_text = fields.Text("New value Text")
    field_name = fields.Char("Technical name", readonly=True)
    field_description = fields.Char("Description", readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        """Ensure field_id is not empty on creation and store field_name and
        field_description."""
        for vals in vals_list:
            if not vals.get("field_id"):
                raise UserError(_("No field defined to create line."))
            field = self.env["ir.model.fields"].sudo().browse(vals["field_id"])
            vals.update(
                {"field_name": field.name, "field_description": field.field_description}
            )
        return super().create(vals_list)

    def write(self, vals):
        """Ensure field_id is set during write and update field_name and
        field_description values."""
        if "field_id" in vals:
            if not vals["field_id"]:
                raise UserError(_("The field 'field_id' cannot be empty."))
            field = self.env["ir.model.fields"].sudo().browse(vals["field_id"])
            vals.update(
                {"field_name": field.name, "field_description": field.field_description}
            )
        return super().write(vals)