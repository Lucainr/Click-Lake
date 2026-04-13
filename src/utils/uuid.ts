const randomPart = () => Math.random().toString(36).slice(2, 10)

export const makeId = (prefix: string) => `${prefix}_${randomPart()}${randomPart()}`
