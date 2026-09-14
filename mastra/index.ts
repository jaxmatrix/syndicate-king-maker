import { Mastra } from '@mastra/core';
import { syndicateKingMakerAgent } from './agent';

export const mastra = new Mastra({
  agents: {
    syndicateKingMakerAgent
  }
});
