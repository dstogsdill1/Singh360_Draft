import { useEffect, useRef } from 'react';
import { Canvas, Rect, Textbox, Circle, Line } from 'fabric';

interface Props {
  serialized: Record<string, unknown>[];
  onSerializedChange: (value: Record<string, unknown>[]) => void;
}

export default function CanvasEditor({ serialized, onSerializedChange }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const fabricRef = useRef<Canvas | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;
    const fabric = new Canvas(canvasRef.current, {
      width: 1550,
      height: 840,
      selection: true,
      backgroundColor: '#ffffff',
    });
    fabricRef.current = fabric;

    const persist = () => {
      const json = fabric.toJSON();
      onSerializedChange((json.objects ?? []) as Record<string, unknown>[]);
    };

    if (serialized.length) {
      fabric.loadFromJSON({ objects: serialized } as any, () => {
        fabric.renderAll();
      });
    }

    fabric.on('object:modified', persist);
    fabric.on('object:added', persist);
    fabric.on('object:removed', persist);

    return () => {
      fabric.dispose();
    };
  }, []);

  const addRect = () => {
    const c = fabricRef.current;
    if (!c) return;
    c.add(new Rect({ left: 100, top: 100, width: 160, height: 80, fill: 'transparent', stroke: '#111', strokeWidth: 1 }));
  };

  const addText = () => {
    const c = fabricRef.current;
    if (!c) return;
    c.add(new Textbox('Text', { left: 150, top: 130, width: 180, fontSize: 18, fill: '#111' }));
  };

  const addCircle = () => {
    const c = fabricRef.current;
    if (!c) return;
    c.add(new Circle({ left: 220, top: 200, radius: 40, fill: 'transparent', stroke: '#111', strokeWidth: 1 }));
  };

  const addLine = () => {
    const c = fabricRef.current;
    if (!c) return;
    c.add(new Line([50, 50, 220, 50], { left: 260, top: 260, stroke: '#111', strokeWidth: 2 }));
  };

  const removeSelected = () => {
    const c = fabricRef.current;
    if (!c) return;
    const obj = c.getActiveObject();
    if (!obj) return;
    c.remove(obj);
  };

  return (
    <div>
      <div className="toolbar-inline">
        <button onClick={addRect}>Rect</button>
        <button onClick={addText}>Text</button>
        <button onClick={addCircle}>Circle</button>
        <button onClick={addLine}>Line</button>
        <button onClick={removeSelected}>Delete</button>
      </div>
      <canvas ref={canvasRef} className="canvas-surface" />
    </div>
  );
}
