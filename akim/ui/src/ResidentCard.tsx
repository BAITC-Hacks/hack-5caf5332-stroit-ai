import { X } from "lucide-react";
import { districts, indicatorNames } from "./data";
import { profiles, residentState, type Resident } from "./population";
import type { Poll } from "./residents";
export default function ResidentCard({
  resident,
  minutes,
  poll,
  stayInside,
  onClose,
}: {
  resident: Resident;
  minutes: number;
  poll: Poll | null;
  stayInside: boolean;
  onClose: () => void;
}) {
  const profile = profiles[resident.profileId],
    state = residentState(resident, minutes, stayInside);
  const cohort = poll?.cohorts?.find(
    (c) =>
      c.districtId === resident.districtId &&
      c.profileId === resident.profileId,
  );
  return (
    <aside className="resident-card glass" aria-label="Житель города">
      <button
        className="icon-button"
        onClick={onClose}
        aria-label="Закрыть жителя"
      >
        <X size={16} />
      </button>
      <div className="eyebrow">СИНТЕТИЧЕСКИЙ ЖИТЕЛЬ #{resident.id + 1}</div>
      <h3>
        {resident.name}, {resident.age}
      </h3>
      <p>
        {profile.name} · {districts[resident.districtIndex].name}
      </p>
      <strong className="resident-activity">
        <i className="live-dot" />
        {state.activity}
      </strong>
      <p>Важно: {profile.needs.map((k) => indicatorNames[k]).join(", ")}.</p>
      <small>
        Дом → {resident.profileId === 2 ? "учёба" : "дела"} → отдых → дом
      </small>
      {cohort && (
        <blockquote>
          {cohort.quote}
          <cite>
            {resident.cohortIndex < cohort.yes
              ? "Поддерживает сценарий"
              : "Не поддерживает сценарий"}{" "}
            · ответ модели для группы
          </cite>
        </blockquote>
      )}
    </aside>
  );
}
