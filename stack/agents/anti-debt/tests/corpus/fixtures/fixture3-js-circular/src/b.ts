// Circular: b.ts imports a.ts which imports b.ts
import { funcA } from './a';

export function funcB(): string {
    return 'B calls ' + funcA();
}
