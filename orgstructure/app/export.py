"""Self-contained HTML and canonical JSON exports."""
import html
import json

LABELS={'created':'Создано','kept':'Сохранено','transformed':'Преобразовано','abolished':'Упразднено','moved':'Перенесено','reworded':'Переформулировано','lost':'Возможная потеря','added':'Добавлено','duplicated':'Дублирование','conflict':'Конфликт интересов'}

def export_json(report):
    return json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2).encode('utf-8')


def export_html(report):
    e=html.escape
    def ref(r):
        context=' · Контекст, не доказательство отсутствия' if r['relation']!='direct' else ''
        return f"<div class='source'><b>{'После' if r.get('side')=='after' else 'До'}: {e(r['doc'])}, §{e(r['clause'])}, абзац {r['paragraph']}{context}</b><blockquote>{e(r['quote'])}</blockquote></div>"
    units=''.join(f"<tr><td>{e(u['name'])}</td><td>{LABELS[u['status']]}</td><td>{ref(dict(u['before_ref'],side='before'))}</td><td>{ref(dict(u['after_ref'],side='after'))}</td></tr>" for u in report['units'])
    functions=''.join(f"<tr><td>{e(f['text'])}</td><td>{LABELS[f['status']]}{' / Дублирование' if f.get('duplicated') else ''}<br>Сходство: {round(f['confidence']*100)}%{'<br>Требует проверки' if f['requires_review'] else ''}</td><td>{ref(f['before'])}</td><td>{ref(f['after'])}</td></tr>" for f in report['functions'])
    risks=''.join(f"<article><h3>{'Мера предотвращения' if r.get('classification')=='safeguard' else LABELS[r['type']]}</h3><p>{e(r['explanation'])}</p><p><b>Рекомендация:</b> {e(r['recommendation'])}</p>{''.join(ref(x) for x in r['evidence'])}</article>" for r in report['risks'])
    conclusion=''.join(f"<li><p>{e(c['text'])}</p><details><summary>Основания</summary>{''.join(ref(r) for r in c['evidence'])}</details></li>" for c in report['conclusion'])
    return f"""<!doctype html><html lang='ru'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Заключение об организационных изменениях</title><style>body{{font:15px/1.6 Arial,sans-serif;color:#18324c;margin:32px auto;padding:0 24px;max-width:1400px}}h1,h2{{line-height:1.3}}table{{border-collapse:collapse;width:100%;font-size:12px}}td,th{{border:1px solid #bccbd3;padding:12px;text-align:left;vertical-align:top}}blockquote{{white-space:pre-wrap;margin:12px 0;padding:12px;background:#f3f6f8;overflow-wrap:anywhere}}article{{border-top:1px solid #bccbd3;margin:24px 0;padding-top:12px}}.scroll{{overflow:auto}}.source{{font-size:12px}}summary{{cursor:pointer}}@media print{{body{{margin:0;padding:0}}thead{{display:table-header-group}}h2,h3{{break-after:avoid}}details{{display:block}}details>*{{display:block}}}}@page{{size:A4 landscape;margin:12mm}}</style><h1>Заключение об организационных изменениях</h1><p>Контур ответственности / Stroit AI. Отчёт {report['run_id']}.</p><p>Режим: {e(report['mode'])}. Выводы рекомендательные и требуют проверки ответственным сотрудником. Контекстные цитаты не доказывают отсутствие функции. Сходство не является вероятностью правильности.</p><h2>Заключение</h2><ol>{conclusion}</ol><h2>Подразделения и роли</h2><div class='scroll'><table><thead><tr><th>Подразделение</th><th>Статус</th><th>До</th><th>После</th></tr></thead><tbody>{units}</tbody></table></div><h2>Сопоставление функций</h2><div class='scroll'><table><thead><tr><th>Функция</th><th>Статус</th><th>До</th><th>После</th></tr></thead><tbody>{functions}</tbody></table></div><h2>Риски и рекомендации</h2>{risks or '<p>Кандидатов на риск не найдено.</p>'}<h2>Метод</h2><p>Разбор → извлечение владельцев → точное сопоставление → TF-IDF слов и символов → правила рисков → проверка дословных цитат → заключение.</p></html>""".encode('utf-8')
