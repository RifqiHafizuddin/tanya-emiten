-- D55/D56: figures are tables (text, no image), charts and diagrams (WebP crops); whole-page crops are gone.
alter table figures drop constraint if exists figures_kind_check;
alter table figures add constraint figures_kind_check check (kind in ('page', 'table', 'chart', 'diagram'));

alter table chunks drop constraint if exists chunks_kind_check;
alter table chunks add constraint chunks_kind_check check (kind in ('text', 'table', 'chart', 'diagram'));
