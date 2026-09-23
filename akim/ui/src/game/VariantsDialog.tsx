import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { budget, simulate } from "../engine";
import { money } from "../money";
import { fmt } from "../planner/analysis";
import { type Variant } from "./variants";

export default function Variants({ variants, canCompare, onClose, onLoad, onCompare, onRename }: {
  variants: Variant[];
  canCompare: boolean;
  onClose: () => void;
  onLoad: (variant: Variant) => void;
  onCompare: (variant: Variant) => void;
  onRename: (id: string, name: string) => boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    return () => element.close();
  }, []);
  return (
    <dialog ref={dialog} className="variants-dialog" aria-labelledby="variants-title" onCancel={(e) => { e.preventDefault(); onClose(); }}>
      <div className="variants-heading">
        <h2 id="variants-title">Сохранённые варианты</h2>
        <button autoFocus type="button" className="icon-button" onClick={onClose} aria-label="Закрыть варианты"><X size={20} /></button>
      </div>
      <p>До трёх вариантов. Нажмите на имя, чтобы переименовать; Enter сохранит его.</p>
      {!variants.length && <p>Пока нет вариантов. Соберите пять решений и сохраните план на листе итога.</p>}
      <ul className="variants-list">
        {variants.map((variant) => (
          <li key={variant.id}>
            <input
              aria-label={`Название варианта ${variant.id}`}
              defaultValue={variant.name}
              maxLength={60}
              onBlur={(e) => {
                const name = e.currentTarget.value.trim() || variant.name;
                const saved = name === variant.name || onRename(variant.id, name);
                e.currentTarget.value = saved ? name : variant.name;
                setError(saved ? "" : "Не удалось сохранить имя: хранилище браузера недоступно.");
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") e.currentTarget.blur();
                if (e.key === "Escape") {
                  e.preventDefault();
                  e.stopPropagation();
                  e.currentTarget.value = variant.name;
                  e.currentTarget.blur();
                }
              }}
            />
            <span>Балл {fmt(simulate(variant.plan).result!.score)} · Бюджет {money(budget(variant.plan))} у.е.</span>
            <div className="variants-actions">
              <button type="button" className="text-button" onClick={() => onLoad(variant)}>Загрузить</button>
              <button type="button" className="text-button" disabled={!canCompare} onClick={() => onCompare(variant)}>Сравнить</button>
            </div>
          </li>
        ))}
      </ul>
      {!canCompare && !!variants.length && <p>Для сравнения сначала соберите текущий план из пяти решений по правилам.</p>}
      {error && <p role="alert">{error}</p>}
    </dialog>
  );
}
