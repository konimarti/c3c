int[char.max][*] a = {
	[0] = {
		[0..char.max] = 1, // #error: The index may must be less than the array length (which was 255).
	},
};
