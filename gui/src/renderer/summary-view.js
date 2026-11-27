// A summary drawn from its data (`outlines --json`, summary_data.py; ADR-0013): the front, then one of two outlines,
// chosen at the top, which stays in view. The points outline says what was said; the argument outline why and how.
// Each unit shows as one line; a switch shows one level more under each line; clicking a unit opens it whole in a
// window of its own, ordered as the outline it came from orders it, and × goes back to where the reader was.

import { element, markdown } from './state.js';

/** @typedef {import('../cli-types').Outlines} Outlines */
/** @typedef {import('../cli-types').Unit} Unit */
/** @typedef {'points' | 'argument'} Outline */

const OUTLINES = /** @type {const} */ ([
  ['points', '要点提纲'],
  ['argument', '论证提纲'],
]);
const SIDES = { unit: '旁支', between: '旁支，插在两个单元之间', line: '旁支，给整条主线做背景' };

/** @type {Outline} */
let chosen = 'points';
let more = false; // one level more under each unit: its aspects (要点), or its reasons and steps (论证)

const clock = (/** @type {number} */ second) => {
  const s = Math.round(second);
  return [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60].map((n) => String(n).padStart(2, '0')).join(':');
};
const inline = (/** @type {string} */ text) => DOMPurify.sanitize(/** @type {string} */ (marked.parseInline(text)));

/**
 * Draws the summary into `article`. `open` opens a link that is not a unit (a picture, the video, a file).
 * @param {HTMLElement} article
 * @param {Outlines} found
 * @param {(href: string) => void} open
 */
export function renderOutlines(article, found, open) {
  const { data, view } = found;
  const units = new Map(data.units.map((unit) => [unit.id, unit]));
  const topics = new Map(data.lines.map((line) => [line.id, line.topic]));
  const head = (/** @type {Unit} */ unit) => unit.items.find((item) => item.id === 'S0')?.text || '';
  // A unit named by its id in the model's text (U004027, U004027.S3) becomes a link that opens it.
  const rich = (/** @type {string} */ text) =>
    (text || '').replace(/ ?\bU(\d{6})(\.S\d+)?\b ?/g, (all, digits, item) => {
      const unit = units.get(`U${digits}`);
      return unit ? `[「${unit.title}」${item ? item.slice(1) : ''}](#U${digits})` : all;
    });

  /** @type {{ id: string, from: Outline }[]} */
  const trail = [];
  const dialog = unitDialog();

  /** @param {HTMLElement} node @param {Outline} from */
  const wire = (node, from) => {
    for (const link of node.querySelectorAll('a[href]')) {
      const href = link.getAttribute('href') || '';
      /** @param {MouseEvent} event */
      const click = (event) => {
        event.preventDefault();
        if (/^#U\d{6}$/.test(href)) openUnit(href.slice(1), from);
        else open(href);
      };
      /** @type {HTMLAnchorElement} */ (link).onclick = click;
    }
    return node;
  };
  const html = (/** @type {string} */ tag, /** @type {string} */ text, from = chosen, className = '') =>
    wire(element(tag, { className, innerHTML: inline(rich(text)) }), from);
  const unitLink = (/** @type {string} */ id, /** @type {Outline} */ from) =>
    element('button', {
      type: 'button',
      className: 'unit-link',
      textContent: `「${units.get(id)?.title || id}」`,
      onclick: () => openUnit(id, from),
    });

  /** Where a unit belongs, in words. @param {Unit} unit */
  const where = (unit) => {
    const attach = unit.attach || {};
    const name = (/** @type {string} */ id) => `「${units.get(id)?.title || id}」`;
    if (attach.line) return `主线：${topics.get(attach.line) || attach.line}`;
    const side = attach.side || {};
    if (side.unit) return `旁支，从${name(side.unit)}岔出`;
    if (side.between) return `旁支，插在${name(side.between[0])}和${name(side.between[1])}之间`;
    if (side.line) return `旁支，给主线「${topics.get(side.line) || side.line}」做背景`;
    return '没有归属';
  };

  /** The items one level down that the outline brings forward, under a unit's line. @param {string} id @param {Outline} from */
  const moreUnder = (id, from) => {
    const unit = units.get(id);
    const shown = view.units[id]?.[from === 'points' ? 'points_more' : 'argument_more'] || [];
    if (!more || !unit || !shown.length) return [];
    const items = shown.map((key) => unit.items.find((item) => item.id === key)).filter((item) => !!item);
    return [element('ul', { className: 'outline-more' }, items.map((item) => html('li', item.text, from)))];
  };

  const points = () =>
    view.points.flatMap((group) => [
      element('h3', { textContent: group.topic || group.line || '' }),
      element(
        'ul',
        { className: 'outline' },
        group.rows.map((row) => {
          const unit = /** @type {Unit} */ (units.get(row.unit));
          const marks = [row.side ? SIDES[row.side] : '', row.conclusion ? '主结论' : ''].filter(Boolean);
          return element('li', { className: 'outline-row', style: `margin-left: ${row.depth * 1.6}em` }, [
            element('code', { textContent: clock(unit.start) }),
            ' ',
            unitLink(row.unit, 'points'),
            ...marks.map((mark) => element('span', { className: 'outline-mark', textContent: mark })),
            '：',
            html('span', head(unit), 'points'),
            ...moreUnder(row.unit, 'points'),
          ]);
        }),
      ),
    ]);

  const argument = () => [
    element(
      'ul',
      { className: 'outline' },
      view.argument.map((row) => {
        const style = `margin-left: ${row.depth * 1.6}em`;
        if (row.unit === null) {
          return element('li', { className: 'outline-row', style }, [
            element('span', { className: 'outline-mark', textContent: '总结者归纳' }),
            html('span', row.text, 'argument'),
          ]);
        }
        const unit = /** @type {Unit} */ (units.get(row.unit));
        const kind = row.kind ? [element('span', { className: 'outline-edge', textContent: row.kind })] : [];
        if (row.repeat) {
          return element('li', { className: 'outline-row', style }, [...kind, unitLink(row.unit, 'argument'), '（在别处展开）']);
        }
        const source = row.source;
        const said = !source
          ? ''
          : source.by === '讲者'
            ? `（讲者 \`${clock(source.time || 0)}\`：${source.said || ''}）`
            : '（总结者归纳）';
        return element('li', { className: 'outline-row', style }, [
          ...kind,
          unitLink(row.unit, 'argument'),
          '：',
          html('span', (row.kind && row.contribution) || head(unit), 'argument'),
          ...(said ? [html('span', said, 'argument', 'muted')] : []),
          ...moreUnder(row.unit, 'argument'),
        ]);
      }),
    ),
  ];

  const body = element('div', { className: 'outline-body' });
  const tabs = OUTLINES.map(([key, label]) =>
    element('button', {
      type: 'button',
      className: 'outline-tab',
      textContent: label,
      onclick: () => {
        chosen = key;
        draw();
      },
    }),
  );
  const toggle = element('input', {
    type: 'checkbox',
    checked: more,
    onchange: () => {
      more = toggle.checked;
      draw();
    },
  });
  const draw = () => {
    tabs.forEach((tab, index) => tab.setAttribute('aria-pressed', String(OUTLINES[index][0] === chosen)));
    body.replaceChildren(...(chosen === 'points' ? points() : argument()));
  };

  /** Opens a unit whole; a unit opened from inside another can be gone back from. @param {string} id @param {Outline} from */
  function openUnit(id, from, again = false) {
    const unit = units.get(id);
    if (!unit) return;
    if (!again) trail.push({ id, from });
    const back = /** @type {HTMLButtonElement} */ (dialog.querySelector('.unit-back'));
    back.hidden = trail.length < 2;
    back.onclick = () => {
      trail.pop();
      const last = trail[trail.length - 1];
      openUnit(last.id, last.from, true);
    };
    /** @type {HTMLElement} */ (dialog.querySelector('.unit-title')).textContent =
      `${unit.title}  ${clock(unit.start)}–${clock(unit.end)}`;
    /** @type {HTMLElement} */ (dialog.querySelector('.unit-where')).textContent = `${unit.kind} · ${where(unit)}`;
    const items = new Map(unit.items.map((item) => [item.id, item]));
    const pictures = new Set(); // a picture used for several items shows under the first of them
    const rows = (view.units[id]?.[from] || []).map(({ item: key, depth }) => {
      const item = /** @type {import('../cli-types').Item} */ (items.get(key));
      const line = element('div', { className: 'unit-item-line' }, [
        element('strong', { textContent: item.id }),
        ...(depth && item.edge ? [element('span', { className: 'outline-edge', textContent: item.edge })] : []),
        ...item.labels.map((label) => element('code', { textContent: label })),
        ...(item.time === null ? [] : [element('code', { textContent: clock(item.time) })]),
        html('span', item.text, from),
      ]);
      const parts = [line];
      if (item.details) parts.push(wire(element('div', { className: 'markdown', innerHTML: markdown(rich(item.details)) }), from));
      for (const picture of item.pictures) {
        if (pictures.has(picture.path)) continue;
        pictures.add(picture.path);
        parts.push(
          element('a', {
            href: '#',
            className: 'unit-picture',
            textContent: picture.caption || '画面',
            onclick: (/** @type {MouseEvent} */ event) => {
              event.preventDefault();
              open(picture.path);
            },
          }),
        );
      }
      return element('li', { className: 'unit-item', style: `margin-left: ${depth * 1.6}em` }, parts);
    });
    /** @type {HTMLElement} */ (dialog.querySelector('.unit-body')).replaceChildren(element('ul', { className: 'unit-items' }, rows));
    if (!dialog.open) dialog.showModal();
    dialog.querySelector('.unit-body')?.scrollTo(0, 0);
  }

  const listed = (/** @type {string[]} */ lines) => {
    const kept = lines.filter((line) => !/^[^：:]{1,12}[：:]\s*$/.test(line)); // an item left empty
    return kept.length ? element('ul', {}, kept.map((line) => html('li', line))) : element('p', { textContent: '无' });
  };
  const front = [
    element('h1', { textContent: data.title }),
    html('p', data.video),
    element('h2', { textContent: '元信息' }),
    listed(data.meta),
    ...(data.notices.length ? [element('h3', { textContent: '需留意' }), listed(data.notices)] : []),
    element('h2', { textContent: '概要' }),
    html('p', data.abstract),
  ];
  const bar = element('div', { className: 'outline-bar' }, [
    element('div', { className: 'outline-tabs' }, tabs),
    element('label', { className: 'outline-more-toggle' }, [toggle, ' 多露一层']),
  ]);
  article.replaceChildren(...front, bar, body, element('h2', { textContent: '需确认' }), listed(data.unsure));
  trail.length = 0;
  dialog.onclose = () => {
    trail.length = 0;
  };
  draw();
}

/** The window a unit opens in, made once. */
function unitDialog() {
  const found = document.getElementById('unit-dialog');
  if (found instanceof HTMLDialogElement) return found;
  const dialog = element('dialog', { id: 'unit-dialog' }, [
    element('div', { className: 'unit-head' }, [
      element('button', { type: 'button', className: 'ghost unit-back', textContent: '←', title: '回到上一个单元' }),
      element('div', { className: 'grow' }, [element('h2', { className: 'unit-title' }), element('p', { className: 'unit-where muted' })]),
      element('button', { type: 'button', className: 'ghost close-x', textContent: '×', title: '关闭', onclick: () => dialog.close() }),
    ]),
    element('div', { className: 'unit-body' }),
  ]);
  document.body.append(dialog);
  return /** @type {HTMLDialogElement} */ (dialog);
}
