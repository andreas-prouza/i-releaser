/*
 * Defaults of bootstrap-table for all tables (docs/features/web-ui-scripts.md).
 *
 * Load after bootstrap-table: <script type="module" src=".../app/tables.js"></script>.
 * Modules run before DOMContentLoaded, so the defaults are set before bootstrap-table builds the tables of data-toggle="table".
 *
 * escape: values of the data are text. A table which bootstrap-table reads from the HTML of a template
 * (cells already escaped by Jinja) sets data-escape="false", or its cells would be shown as HTML source.
 */

const $ = window.jQuery;

if ($?.fn?.bootstrapTable) {
    $.extend($.fn.bootstrapTable.defaults, {
        escape: true,
        pageSize: 25,
        pageList: [10, 25, 50, 100, 'all'],
        buttonsClass: 'outline-secondary',
        iconsPrefix: 'bi',
        undefinedText: '–',
        formatNoMatches: () => 'Nothing found',
    });
}
