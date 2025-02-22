import { Container, Filter } from "pixi.js";


export function addFilter(element: Container, filter: Filter): Filter {
    if (Array.isArray(element.filters)) {
        element.filters = [...element.filters, filter];
    }
    else if (element.filters) {
        element.filters = [element.filters, filter];
    }
    else {
        element.filters = [filter];
    }
    return filter;
}


export function removeFilter(element: Container, filter: Filter) {
    if (Array.isArray(element.filters)) {
        element.filters = element.filters.filter(f => f != filter);
    }
    else if (element.filters) {
        if (element.filters == filter) {
            element.filters = [];
        }
    }
}


export function applyHoverFilter(element: Container, filter: Filter) {
    element.eventMode = "dynamic";

    element.addEventListener("mouseenter", () => {
        addFilter(element, filter);
    });

    element.addEventListener("mouseleave", () => {
        removeFilter(element, filter);
    });
}
