import { useEffect, useRef } from "react";
import { ControlButton, Controls, useReactFlow } from "@xyflow/react";

import Icon from "./Icon.jsx";

export default function GraphControls({ isGraphMaximized, onToggleGraphMaximized }) {
  const { fitView } = useReactFlow();
  const previousMaximizedRef = useRef(isGraphMaximized);

  useEffect(() => {
    if (previousMaximizedRef.current === isGraphMaximized) {
      return undefined;
    }
    previousMaximizedRef.current = isGraphMaximized;

    const resizeTimer = window.setTimeout(() => {
      fitView({ duration: 300 });
    }, 320);

    return () => window.clearTimeout(resizeTimer);
  }, [fitView, isGraphMaximized]);

  return (
    <Controls
      showFitView={false}
      showInteractive={false}
      showZoom
      position="bottom-right"
    >
      <ControlButton
        onClick={onToggleGraphMaximized}
        title={
          isGraphMaximized ? "Restore split layout" : "Expand graph layout"
        }
        aria-label={
          isGraphMaximized ? "Restore split layout" : "Expand graph layout"
        }
        aria-pressed={isGraphMaximized}
      >
        <Icon
          name={isGraphMaximized ? "collapse" : "expand"}
          className="size-4"
        />
      </ControlButton>
    </Controls>
  );
}
