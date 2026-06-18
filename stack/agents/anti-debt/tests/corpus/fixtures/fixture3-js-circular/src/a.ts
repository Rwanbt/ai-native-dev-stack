// fixture3-js-circular — circular dependency between a.ts and b.ts
import { funcB } from './b';

export function funcA(): string {
    return 'A calls ' + funcB();
}
