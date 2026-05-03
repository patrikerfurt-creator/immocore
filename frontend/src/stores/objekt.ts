import { create } from 'zustand'

interface ObjektState {
  selectedId: string | null
  selectedName: string | null
  selectedNummer: string | null
  selectedTyp: string | null
  setSelected: (id: string, name: string, nummer: string, typ: string) => void
  clearSelected: () => void
}

export const useObjektStore = create<ObjektState>((set) => ({
  selectedId: null,
  selectedName: null,
  selectedNummer: null,
  selectedTyp: null,
  setSelected: (id, name, nummer, typ) =>
    set({ selectedId: id, selectedName: name, selectedNummer: nummer, selectedTyp: typ }),
  clearSelected: () =>
    set({ selectedId: null, selectedName: null, selectedNummer: null, selectedTyp: null }),
}))
