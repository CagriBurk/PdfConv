import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  rectSortingStrategy,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { ReactNode } from "react";

interface Props<T> {
  items: T[];
  getKey: (item: T) => string;
  onChange: (items: T[]) => void;
  render: (item: T, index: number) => ReactNode;
  grid?: boolean;
}

/** Sürükleyerek (ya da odaklanıp Boşluk + oklarla) sıralanan liste. */
export default function SortableList<T>({ items, getKey, onChange, render, grid }: Props<T>) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const keys = items.map(getKey);
  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    onChange(arrayMove(items, keys.indexOf(String(active.id)), keys.indexOf(String(over.id))));
  };
  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
      <SortableContext items={keys} strategy={grid ? rectSortingStrategy : verticalListSortingStrategy}>
        <ul className={grid ? "sortable-grid" : "sortable-list"}>
          {items.map((item, i) => (
            <SortableItem key={keys[i]} id={keys[i]}>
              {render(item, i)}
            </SortableItem>
          ))}
        </ul>
      </SortableContext>
    </DndContext>
  );
}

function SortableItem({ id, children }: { id: string; children: ReactNode }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  return (
    <li
      ref={setNodeRef}
      className={`sortable-item${isDragging ? " dragging" : ""}`}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      {...attributes}
      {...listeners}
    >
      {children}
    </li>
  );
}
