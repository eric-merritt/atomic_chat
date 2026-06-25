import { type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { Icon } from "../atoms/Icon";
import { ToolExplorer } from "./ToolExplorer";
import { GraphExplorer } from "./GraphExplorer";

interface SidebarProps {
  expanded: boolean;
  onToggle: () => void;
  location: string;
  children?: ReactNode;
  header: string;
}

export function Sidebar({
  expanded,
  onToggle,
  location,
  children,
  header,
}: SidebarProps) {
  location = useLocation().pathname;
  header = location == "/" ? "Tools" : "Graph Tools";
  children = location == "/" ? <ToolExplorer /> : <GraphExplorer />;

  return (
    <div
      id="sidebar"
      className={`flex border border-[var(--accent)] rounded-[14px] m-2 shadow-[0_4px_24px_rgba(0,0,0,0.15)] transition-colors ${
        expanded
          ? "backdrop-blur-md"
          : "bg-transparent hover:backdrop-blur-md cursor-pointer"
      }`}
    >
      {/* Main content column */}
      <div
        className="flex-1 flex flex-col overflow-hidden"
        onClick={expanded ? undefined : onToggle}
      >
        <div className="text-sm font-semibold text-[var(--text)] py-2 pl-4 text-center underline">
          {header}
        </div>
        {expanded ? children : ""}
      </div>

      {/* Chevron column */}
      <div
        className="flex items-center justify-center cursor-pointer transition-colors"
        onClick={onToggle}
        title="Toggle tools"
      >
        <Icon
          name="chevron"
          size={18}
          className={`text-[var(--accent)] transition-all ${expanded ? "rotate-180" : ""}`}
        />
      </div>
    </div>
  );
}
