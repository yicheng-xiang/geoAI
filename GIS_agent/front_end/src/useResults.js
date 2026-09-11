import { useCallback, useReducer } from 'react';
import { PAGE_SIZE, tableRows } from './resultsModel.js';
const initial = { results: [], tabs: [], active: null, views: {}, selection: null, hidden: null };
export function resultsReducer(state, action) {
  switch (action.type) {
    case 'reset': return initial;
    case 'receive': {
      const known = new Set(state.results.map((r) => r.id));
      const added = action.results.filter((r) => !known.has(r.id));
      return { ...state, results: action.results, tabs: [...state.tabs, ...added.map((r) => r.id)],
        active: added.at(-1)?.id || state.active, selection: added.length ? null : state.selection,
        hidden: added.length ? null : state.hidden };
    }
    case 'open': return { ...state, active: action.id, tabs: [...new Set([...state.tabs, action.id])], selection: null, hidden: null };
    case 'close': {
      const tabs = state.tabs.filter((id) => id !== action.id);
      return { ...state, tabs, active: state.active === action.id ? tabs.at(-1) || null : state.active, selection: null, hidden: null };
    }
    case 'view': return { ...state, views: { ...state.views, [state.active]: { ...state.views[state.active], ...action.patch } } };
    case 'clear': return { ...state, selection: null, hidden: null };
    case 'select': return { ...state, selection: action.selection, hidden: null };
    case 'map': {
      const result = state.results.find((r) => r.id === action.resultId);
      const row = result?.rows.find((r) => r.id === action.rowId);
      if (!row) return state;
      const view = state.views[result.id] || {};
      const rows = tableRows(result, action.clearFilter ? { ...view, query: '' } : view);
      const index = rows.findIndex((r) => r.id === row.id);
      return { ...state, active: result.id, tabs: [...new Set([...state.tabs, result.id])],
        hidden: index < 0 ? { resultId: result.id, rowId: row.id } : null,
        selection: index < 0 ? null : { resultId: result.id, rowId: row.id, featureId: row.feature_id, token: action.token, focus: false },
        views: { ...state.views, [result.id]: { ...view, ...(action.clearFilter ? { query: '' } : {}), page: Math.max(0, Math.floor(index / PAGE_SIZE)) } } };
    }
    default: return state;
  }
}
export default function useResults() {
  const [state, dispatch] = useReducer(resultsReducer, initial);
  const receive = useCallback((payload) => {
    if (Array.isArray(payload.results)) dispatch({ type: 'receive', results: payload.results });
  }, []);
  const onFeatureClick = useCallback((props) => {
    dispatch({ type: 'map', resultId: props._result_id, rowId: props._result_row_id, token: crypto.randomUUID() });
  }, []);
  return { state, dispatch, receive, onFeatureClick };
}
