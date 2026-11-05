// next/cache needs a server runtime; tests treat unstable_cache as a pass-through.
module.exports = { unstable_cache: (fn) => fn };
